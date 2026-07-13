import requests
import os
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
    if request.status_code == 200:
        return request
    raise RuntimeError(func_name, ' has failed with a',
                       request.status_code, request.text, QUERY_COUNT)


def graph_repos_stars(count_type: str, owner_affiliation: list[str], cursor: str | None = None) -> int:
    """
    Uses GitHub's GraphQL v4 API to return my total repository or star count.
    """

    query_count('graph_repos_stars')
    query = '''
    query ($owner_affiliation: [RepositoryAffiliation], $login: String!, $cursor: String) {
        user(login: $login) {
            repositories(first: 100, after: $cursor, ownerAffiliations: $owner_affiliation) {
                totalCount
                edges {
                    node {
                        ... on Repository {
                            nameWithOwner
                            stargazers {
                                totalCount
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
    request = simple_request(graph_repos_stars.__name__, query, variables)
    # simple_request already guaranteed a 200 (it raises otherwise), so no re-check.
    repos = request.json()['data']['user']['repositories']
    if count_type == 'repos':
        return int(repos['totalCount'])
    if count_type == 'stars':
        return stars_counter(repos['edges'])
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
    # If repository data has another page
    if request.json()['data']['user']['repositories']['pageInfo']['hasNextPage']:
        # Add on to the LoC count
        edges += request.json()['data']['user']['repositories']['edges']
        return loc_query(owner_affiliation, comment_size, force_cache, request.json()['data']['user']['repositories']['pageInfo']['endCursor'], edges)
    else:
        return cache_builder(edges + request.json()['data']['user']['repositories']['edges'], comment_size, force_cache)


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
    for node in data:
        total_stars += node['node']['stargazers']['totalCount']
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
