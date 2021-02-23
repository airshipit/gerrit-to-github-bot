# Licensed under the Apache License, Version 2.0 (the 'License');
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#     http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an 'AS IS' BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.
from datetime import datetime
import logging
import re

import github
from github.Issue import Issue
from github.IssueComment import IssueComment

from gerrit_to_github_issues import errors

LOG = logging.getLogger(__name__)


def construct_issue_list(match_list: list) -> list:
    new_list = []
    for issue in match_list:
        try:
            new_list.append(int(issue))
        except ValueError:
            LOG.warning(f'Value {issue} could not be converted to `int` type')
    return new_list


def parse_issue_number(commit_msg: str) -> dict:
    # Searches for Relates-To or Closes tags first to match and return
    LOG.debug(f'Parsing commit message: {commit_msg}')
    related = re.findall(r'(?<=Relates-To: #)(.*?)(?=\n)', commit_msg)
    LOG.debug(f'Captured related issues: {related}')
    closes = re.findall(r'(?<=Closes: #)(.*?)(?=\n)', commit_msg)
    LOG.debug(f'Captured closes issues: {closes}')
    if related or closes:
        return {
            'related': construct_issue_list(related),
            'closes': construct_issue_list(closes)
        }
    # If no Relates-To or Closes tags are defined, find legacy [#X] style tags
    LOG.debug('Falling back to legacy tags')
    legacy_matches = re.findall(r'(?<=\[#)(.*?)(?=\])', commit_msg)
    LOG.debug(f'Captured legacy issues: {legacy_matches}')
    if not legacy_matches:
        return {}
    return {
        'related': construct_issue_list(legacy_matches)
    }


def remove_duplicated_issue_numbers(issue_dict: dict) -> dict:
    if 'closes' in issue_dict:
        issue_dict['related'] = [x for x in issue_dict['related'] if x not in issue_dict['closes']]
    return issue_dict


def get_client(github_user: str, github_pw: str, github_token: str) -> github.Github:
    if github_token:
        return github.Github(github_token)

    if github_user and github_pw:
        return github.Github(github_user, github_pw)

    raise errors.GithubConfigurationError


def get_bot_comment(issue: Issue, bot_name: str, ps_number: str) -> IssueComment:
    for i in issue.get_comments():
        if i.user.login == bot_name and str(ps_number) in i.body:
            return i


def assign_issues(repo: github.Repository):
    open_issues = [i for i in repo.get_issues() if i.state == 'open']
    for issue in open_issues:
        try_assign(issue)


def try_assign(issue: github.Issue):
    # find the most recent assignment request
    assignment_request = None
    for comment in issue.get_comments().reversed:
        if '/assign' in comment.body:
            assignment_request = comment
            break
    if not assignment_request:
        # Looks like no one wants this issue
        return

    if not issue.assignees:
        # If no one has been assigned yet, let the user take the issue
        issue.add_to_assignees(assignment_request.user)
        issue.create_comment(f'assigned {assignment_request.user.login}')
        return

    # Disable this logic due to an issue. Will re-visit this logic
    # and will be re-enabled after testing
    #if issue_age(issue) > 30:
    #    # If the issue is 1 months old and the original assignees haven't
    #    # closed it yet, let's assume that they've stopped working on it and
    #    # allow the new user to have this issue
    #    old_assignees = issue.assignees
    #    for assignee in old_assignees:
    #        issue.remove_from_assignees(assignee)
    #    issue.add_to_assignees(assignment_request.user)
    #    comment_body = f'unassigned: {", ".join([str(a) for a in old_assignees])}\n' + \
    #                   f'assigned: {assignment_request.user.login}'
    #    issue.create_comment(comment_body)
    #    return

    # If we've made it here, a user has requested to be assigned to a non-stale
    # issue which is already assigned. Just notify the core team and let them
    # handle the conflict.
    comment_body = f'Unable to assign {assignment_request.user.login}. Please ' + \
                   f'contact a member of the @airshipit/airship-cores team for ' + \
                   f'help with assignments.'
    issue.create_comment(comment_body)


def issue_age(issue):
    return (datetime.now() - issue.created_at).days
