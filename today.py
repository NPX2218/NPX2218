import requests
import os
import sys
import hashlib
from typing import Any

# Fine-grained personal access token with All Repositories access:
# Account permissions: read:Followers, read:Starring, read:Watching
# Repository permissions: read:Commit statuses, read:Contents, read:Issues, read:Metadata, read:Pull Requests
HEADERS = {'authorization': 'token ' + os.environ['ACCESS_TOKEN']}
USER_NAME = os.environ['USER_NAME']  # 'NPX2218'
QUERY_COUNT = {'user_getter': 0, 'follower_getter': 0, 'graph_repos_stars': 0,
               'recursive_loc': 0, 'loc_query': 0}

# Set by build_readme.py after user_getter(); loc_counter_one_repo compares
# each commit's author against this to decide which commits are yours.
OWNER_ID: dict[str, str] | None = None


def simple_request(func_name: str, query: str, variables: dict[str, Any]) -> requests.Response:
    """
    Returns a request, or raises an Exception if the response does not succeed.
    """
    request = requests.post('https://api.github.com/graphql',
                            json={'query': query, 'variables': variables},
                            headers=HEADERS, timeout=None)
    if request.status_code != 200:
        raise RuntimeError(func_name, ' has failed with a',
                           request.status_code, request.text, QUERY_COUNT)

    # GitHub answers a partially-failed GraphQL query with 200 + an "errors"
    # array, putting nulls where it could not resolve a field. The old code
    # only checked the status code, so those errors were discarded and the
    # nulls surfaced much later as an unreadable "'NoneType' object is not
    # subscriptable". Two outcomes, two handlings:
    #   - data missing entirely -> nothing to salvage, raise with the reason.
    #   - data present -> log and continue; live_nodes() drops the null repos,
    #     so one unreadable repo can't red-line the whole weekly refresh.
    body = request.json()
    if 'errors' in body:
        print(f'WARNING: {func_name} GraphQL errors: {body["errors"]}',
              file=sys.stderr)
        if body.get('data') is None:
            raise RuntimeError(func_name, ' returned no data',
                               body['errors'], QUERY_COUNT)
    return request


def live_nodes(edges: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """
    Drop edges whose node came back null.

    Every consumer below dereferences edge['node'][...] directly, so a single
    null node takes down the entire run — which is what broke the scheduled
    build on 2026-08-16 and the three scheduled runs after it. Filtering once
    here, at the fetch boundary, keeps null-handling out of stars_counter,
    cache_builder and flush_cache.
    """
    return [edge for edge in edges if edge.get('node')]


def graph_repos_stars(count_type: str, owner_affiliation: list[str], cursor: str | None = None,
                      total_stars: int = 0) -> int:
    """
    Uses GitHub's GraphQL v4 API to return my total repository or star count.
    """

    query_count('graph_repos_stars')
    # Page size is 60, not the 100 this used to request, to match loc_query --
    # see its docstring: GitHub 502s on larger repository pages and throttles
    # on smaller ones. 100 was also silently wrong in a second way: the query
    # selected pageInfo but never followed it, so the star total stopped at the
    # first page. Invisible at 57 repos, an undercount the moment there are
    # more than a page's worth. Both found while tracing the 2026-08-16 CI
    # break; keep this number in step with loc_query's.
    query = '''
    query ($owner_affiliation: [RepositoryAffiliation], $login: String!, $cursor: String) {
        user(login: $login) {
            repositories(first: 60, after: $cursor, ownerAffiliations: $owner_affiliation) {
                totalCount
                edges {
                    node {
                        ... on Repository {
                            nameWithOwner
                            # stargazerCount, not stargazers { totalCount }.
                            # The stargazers *connection* resolves the list of
                            # users who starred, which the CI token may not
                            # read: on 2026-09-13 every repo came back
                            # FORBIDDEN "Resource not accessible by personal
                            # access token" on that exact path, and the star
                            # total silently published as 0. stargazerCount is
                            # a plain scalar on Repository and needs only
                            # Metadata read.
                            stargazerCount
                        }
                    }
                }
                pageInfo {
                    endCursor
                    hasNextPage
                }
            }
        }
    }'''
    variables = {'owner_affiliation': owner_affiliation,
                 'login': USER_NAME, 'cursor': cursor}
    request = simple_request(graph_repos_stars.__name__, query, variables)
    # simple_request already guaranteed a 200 (it raises otherwise), so no re-check.
    repos = request.json()['data']['user']['repositories']
    if count_type == 'repos':
        # totalCount is the server-side total, so this needs no pagination.
        return int(repos['totalCount'])
    if count_type == 'stars':
        total_stars += stars_counter(repos['edges'])
        if repos['pageInfo']['hasNextPage']:
            return graph_repos_stars(count_type, owner_affiliation,
                                     repos['pageInfo']['endCursor'], total_stars)
        return total_stars
    # Any other count_type is a caller bug — fail loudly instead of falling off
    # the end and returning None (which is what mypy's "missing return" flagged).
    raise ValueError(f"unknown count_type: {count_type!r}")


def recursive_loc(owner: str, repo_name: str, data: list[str], cache_comment: list[str],
                  addition_total: int = 0, deletion_total: int = 0, my_commits: int = 0,
                  cursor: str | None = None) -> tuple[int, int, int]:
    """
    Uses GitHub's GraphQL v4 API and cursor pagination to fetch 100 commits from a repository at a time
    """
    query_count('recursive_loc')
    query = '''
    query ($repo_name: String!, $owner: String!, $cursor: String) {
        repository(name: $repo_name, owner: $owner) {
            defaultBranchRef {
                target {
                    ... on Commit {
                        history(first: 100, after: $cursor) {
                            totalCount
                            edges {
                                node {
                                    ... on Commit {
                                        committedDate
                                    }
                                    author {
                                        user {
                                            id
                                        }
                                    }
                                    deletions
                                    additions
                                }
                            }
                            pageInfo {
                                endCursor
                                hasNextPage
                            }
                        }
                    }
                }
            }
        }
    }'''
    variables = {'repo_name': repo_name, 'owner': owner, 'cursor': cursor}
    # I cannot use simple_request(), because I want to save the file before raising Exception
    request = requests.post('https://api.github.com/graphql',
                            json={'query': query, 'variables': variables}, headers=HEADERS)
    if request.status_code == 200:
        # Only count commits if repo isn't empty
        if request.json()['data']['repository']['defaultBranchRef'] != None:
            return loc_counter_one_repo(owner, repo_name, data, cache_comment, request.json()['data']['repository']['defaultBranchRef']['target']['history'], addition_total, deletion_total, my_commits)
        else:
            # Empty repo: return a zero *tuple*, not bare 0. cache_builder unpacks
            # this result as loc[0]/loc[1]/loc[2], so 0 would raise TypeError.
            return (0, 0, 0)
    # saves what is currently in the file before this program crashes
    force_close_file(data, cache_comment)
    if request.status_code == 403:
        raise Exception(
            'Too many requests in a short amount of time!\nYou\'ve hit the non-documented anti-abuse limit!')
    raise Exception('recursive_loc() has failed with a',
                    request.status_code, request.text, QUERY_COUNT)


def loc_counter_one_repo(owner: str, repo_name: str, data: list[str], cache_comment: list[str],
                         history: dict[str, Any], addition_total: int, deletion_total: int,
                         my_commits: int) -> tuple[int, int, int]:
    """
    Recursively call recursive_loc (since GraphQL can only search 100 commits at a time)
    only adds the LOC value of commits authored by me
    """
    for node in history['edges']:
        if node['node']['author']['user'] == OWNER_ID:
            my_commits += 1
            addition_total += node['node']['additions']
            deletion_total += node['node']['deletions']

    if history['edges'] == [] or not history['pageInfo']['hasNextPage']:
        return addition_total, deletion_total, my_commits
    else:
        return recursive_loc(owner, repo_name, data, cache_comment, addition_total, deletion_total, my_commits, history['pageInfo']['endCursor'])


def loc_query(owner_affiliation: list[str], comment_size: int = 0, force_cache: bool = False,
              cursor: str | None = None,
              edges: list[dict[str, Any]] | None = None) -> list[int]:
    """
    Uses GitHub's GraphQL v4 API to query all the repositories I have access to (with respect to owner_affiliation)
    Queries 60 repos at a time, because larger queries give a 502 timeout error and smaller queries send too many
    requests and also give a 502 error.
    Returns the total number of lines of code in all repositories
    """
    query_count('loc_query')
    # Default to None (not []) and seed a fresh list here, so the accumulator
    # isn't one shared list reused across separate top-level calls — the classic
    # Python mutable-default-argument bug.
    if edges is None:
        edges = []
    query = '''
    query ($owner_affiliation: [RepositoryAffiliation], $login: String!, $cursor: String) {
        user(login: $login) {
            repositories(first: 60, after: $cursor, ownerAffiliations: $owner_affiliation) {
            edges {
                node {
                    ... on Repository {
                        nameWithOwner
                        defaultBranchRef {
                            target {
                                ... on Commit {
                                    history {
                                        totalCount
                                        }
                                    }
                                }
                            }
                        }
                    }
                }
                pageInfo {
                    endCursor
                    hasNextPage
                }
            }
        }
    }'''
    variables = {'owner_affiliation': owner_affiliation,
                 'login': USER_NAME, 'cursor': cursor}
    request = simple_request(loc_query.__name__, query, variables)
    # One parse, one lookup -- this used to re-run request.json() four times.
    # live_nodes() strips repos GitHub returned as null, so cache_builder and
    # flush_cache below can keep dereferencing node[...] without a guard.
    repos = request.json()['data']['user']['repositories']
    edges += live_nodes(repos['edges'])
    # If repository data has another page
    if repos['pageInfo']['hasNextPage']:
        # Add on to the LoC count
        return loc_query(owner_affiliation, comment_size, force_cache,
                         repos['pageInfo']['endCursor'], edges)
    else:
        return cache_builder(edges, comment_size, force_cache)


def cache_builder(edges: list[dict[str, Any]], comment_size: int, force_cache: bool,
                  loc_add: int = 0, loc_del: int = 0) -> list[int]:
    """
    Checks each repository in edges to see if it has been updated since the last time it was cached
    If it has, run recursive_loc on that repository to update the LOC count
    """
    cached = True  # Assume all repositories are cached
    # Create a unique filename for each user
    filename = 'cache/' + \
        hashlib.sha256(USER_NAME.encode('utf-8')).hexdigest()+'.txt'
    try:
        with open(filename, 'r') as f:
            data = f.readlines()
    except FileNotFoundError:  # If the cache file doesn't exist, create it
        data = []
        if comment_size > 0:
            for _ in range(comment_size):
                data.append(
                    'This line is a comment block. Write whatever you want here.\n')
        with open(filename, 'w') as f:
            f.writelines(data)

    # If the number of repos has changed, or force_cache is True
    if len(data)-comment_size != len(edges) or force_cache:
        cached = False
        flush_cache(edges, filename, comment_size)
        with open(filename, 'r') as f:
            data = f.readlines()

    cache_comment = data[:comment_size]  # save the comment block
    data = data[comment_size:]  # remove those lines
    for index in range(len(edges)):
        repo_hash, commit_count, *__ = data[index].split()
        if repo_hash == hashlib.sha256(edges[index]['node']['nameWithOwner'].encode('utf-8')).hexdigest():
            try:
                if int(commit_count) != edges[index]['node']['defaultBranchRef']['target']['history']['totalCount']:
                    # if commit count has changed, update loc for that repo
                    owner, repo_name = edges[index]['node']['nameWithOwner'].split(
                        '/')
                    loc = recursive_loc(owner, repo_name, data, cache_comment)
                    data[index] = repo_hash + ' ' + str(edges[index]['node']['defaultBranchRef']['target']['history']
                                                        ['totalCount']) + ' ' + str(loc[2]) + ' ' + str(loc[0]) + ' ' + str(loc[1]) + '\n'
            except TypeError:  # If the repo is empty
                data[index] = repo_hash + ' 0 0 0 0\n'
    with open(filename, 'w') as f:
        f.writelines(cache_comment)
        f.writelines(data)
    for line in data:
        cols = line.split()          # renamed from `loc` — that name held a tuple above
        loc_add += int(cols[3])
        loc_del += int(cols[4])
    return [loc_add, loc_del, loc_add - loc_del, cached]


def flush_cache(edges: list[dict[str, Any]], filename: str, comment_size: int) -> None:
    """
    Wipes the cache file
    This is called when the number of repositories changes or when the file is first created
    """
    with open(filename, 'r') as f:
        data: list[str] = []
        if comment_size > 0:
            data = f.readlines()[:comment_size]  # only save the comment
    with open(filename, 'w') as f:
        f.writelines(data)
        for node in edges:
            f.write(hashlib.sha256(node['node']['nameWithOwner'].encode(
                'utf-8')).hexdigest() + ' 0 0 0 0\n')


def force_close_file(data: list[str], cache_comment: list[str]) -> None:
    """
    Forces the file to close, preserving whatever data was written to it
    This is needed because if this function is called, the program would've crashed before the file is properly saved and closed
    """
    filename = 'cache/' + \
        hashlib.sha256(USER_NAME.encode('utf-8')).hexdigest()+'.txt'
    with open(filename, 'w') as f:
        f.writelines(cache_comment)
        f.writelines(data)
    print('There was an error while writing to the cache file. The file,',
          filename, 'has had the partial data saved and closed.')


def stars_counter(data: list[dict[str, Any]]) -> int:
    """
    Count total stars in repositories owned by me
    """
    total_stars = 0
    unreadable = 0
    for edge in data:
        # Takes raw edges, not live_nodes() output: a partial response can null
        # the whole node OR just the star field, and both mean "unreadable".
        # Counting them here keeps the readable/unreadable split in one place.
        node = edge.get('node')
        count = node.get('stargazerCount') if node else None
        if count is None:
            unreadable += 1
            continue
        total_stars += count

    if unreadable:
        print(f'WARNING: {unreadable}/{len(data)} repositories returned no '
              'star count; total is an undercount', file=sys.stderr)
    # Publishing a confidently wrong 0 to a public profile is worse than a red
    # build: on 2026-09-13 a token that could not read star counts turned a
    # real 14 into a published 0. If nothing was readable, fail instead.
    if data and unreadable == len(data):
        raise RuntimeError(
            'every repository returned an unreadable star count -- refusing to '
            'publish 0. ACCESS_TOKEN is likely missing repository Metadata '
            'read; see the GraphQL FORBIDDEN warnings above.')
    return total_stars


def commit_counter(comment_size: int) -> int:
    """
    Counts up my total commits, using the cache file created by cache_builder.
    """
    total_commits = 0
    # Use the same filename as cache_builder
    filename = 'cache/' + \
        hashlib.sha256(USER_NAME.encode('utf-8')).hexdigest()+'.txt'
    with open(filename, 'r') as f:
        data = f.readlines()
    cache_comment = data[:comment_size]  # save the comment block
    data = data[comment_size:]  # remove those lines
    for line in data:
        total_commits += int(line.split()[2])
    return total_commits


def user_getter(username: str) -> tuple[dict[str, str], str]:
    """
    Returns the account ID and creation time of the user
    """
    query_count('user_getter')
    query = '''
    query($login: String!){
        user(login: $login) {
            id
            createdAt
        }
    }'''
    variables = {'login': username}
    request = simple_request(user_getter.__name__, query, variables)
    return {'id': request.json()['data']['user']['id']}, request.json()['data']['user']['createdAt']


def follower_getter(username: str) -> int:
    """
    Returns the number of followers of the user
    """
    query_count('follower_getter')
    query = '''
    query($login: String!){
        user(login: $login) {
            followers {
                totalCount
            }
        }
    }'''
    request = simple_request(follower_getter.__name__,
                             query, {'login': username})
    return int(request.json()['data']['user']['followers']['totalCount'])


def query_count(funct_id: str) -> None:
    """
    Counts how many times the GitHub GraphQL API is called
    """
    global QUERY_COUNT
    QUERY_COUNT[funct_id] += 1
