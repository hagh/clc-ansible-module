#!/usr/bin/python

# CenturyLink Cloud Ansible Modules.
#
# These Ansible modules enable the CenturyLink Cloud v2 API to be called
# from an within Ansible Playbook.
#
# This file is part of CenturyLink Cloud, and is maintained
# by the Workflow as a Service Team
#
# Copyright 2015 CenturyLink Cloud
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#    http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.
#
# CenturyLink Cloud: http://www.CenturyLinkCloud.com
# API Documentation: https://www.centurylinkcloud.com/api-docs/v2/
#

DOCUMENTATION = '''
module: clc_server
short_desciption: Create, Delete and Restore server snapshots in CenturyLink Cloud.
description:
  - An Ansible module to Create, Delete and Restore server snapshots in CenturyLink Cloud.
options:
  server_ids:
    description:
      - A list of server Ids to snapshot.
    default: []
    required: True
    aliases: []
  expiration_days:
    description:
      - The number of days to keep the server snapshot before it expires.
    default: 7
    required: False
    aliases: []
  state:
    description:
      - The state to insure that the provided resources are in.
    default: 'present'
    required: False
    choices: ['present', 'absent', 'restore']
    aliases: []
  wait:
    description:
      - Whether to wait for the provisioning tasks to finish before returning.
    default: True
    required: False
    choices: [ True, False]
    aliases: []
'''

EXAMPLES = '''
# Note - You must set the CLC_V2_API_USERNAME And CLC_V2_API_PASSWD Environment variables before running these examples

- name: Create server snapshot
  clc_server_snapshot:
    server_ids:
        - UC1WFSDTEST01
        - UC1WFSDTEST02
    expiration_days: 10
    wait: True
    state: present

- name: Restore server snapshot
  clc_server_snapshot:
    server_ids:
        - UC1WFSDTEST01
        - UC1WFSDTEST02
    wait: True
    state: restore

- name: Delete server snapshot
  clc_server_snapshot:
    server_ids:
        - UC1WFSDTEST01
        - UC1WFSDTEST02
    wait: True
    state: absent
'''

import socket
#
#  Requires the clc-python-sdk.
#  sudo pip install clc-sdk
#
try:
    import clc as clc_sdk
    from clc import CLCException
except ImportError:
    clc_found = False
    clc_sdk = None
else:
    CLC_FOUND = True


class ClcSnapshot():

    clc = clc_sdk
    module = None

    STATSD_HOST = '64.94.114.218'
    STATSD_PORT = 2003
    STATS_SNAPSHOT_CREATE = 'stats_counts.wfaas.clc.ansible.snapshot.create'
    STATS_SNAPSHOT_DELETE = 'stats_counts.wfaas.clc.ansible.snapshot.delete'
    STATS_SNAPSHOT_RESTORE = 'stats_counts.wfaas.clc.ansible.snapshot.restore'
    SOCKET_CONNECTION_TIMEOUT = 3

    def __init__(self, module):
        self.module = module
        if not CLC_FOUND:
            self.module.fail_json(
                msg='clc-python-sdk required for this module')

    def process_request(self):
        """
        Process the request - Main Code Path
        :return: Returns with either an exit_json or fail_json
        """
        p = self.module.params

        if not CLC_FOUND:
            self.module.fail_json(
                msg='clc-python-sdk required for this module')

        server_ids = p['server_ids']
        expiration_days = p['expiration_days']
        state = p['state']
        command_list = []
        requests = []
        if not server_ids:
            return self.module.fail_json(msg='List of Server ids are required')

        self._set_clc_credentials_from_env()
        if state == 'present':
            changed, requests, changed_servers = self.ensure_server_snapshot_present(server_ids=server_ids,
                                                                                     expiration_days=expiration_days)
        elif state == 'absent':
            changed, requests, changed_servers = self.ensure_server_snapshot_absent(
                server_ids=server_ids)
        elif state == 'restore':
            changed, requests, changed_servers = self.ensure_server_snapshot_restore(
                server_ids=server_ids)
        else:
            return self.module.fail_json(msg="Unknown State: " + state)

        self._wait_for_requests_to_complete(requests)
        return self.module.exit_json(
            changed=changed,
            server_ids=changed_servers)

    def ensure_server_snapshot_present(self, server_ids, expiration_days):
        result = []
        changed = False
        try:
            servers = self._get_servers_from_clc(
                server_ids,
                'Failed to obtain server list from the CLC API')
            servers_to_change = [
                server for server in servers if len(
                    server.GetSnapshots()) == 0]
            for server in servers_to_change:
                changed = True
                if not self.module.check_mode:
                    res = server.CreateSnapshot(
                        delete_existing=True,
                        expiration_days=expiration_days)
                    ClcSnapshot._push_metric(
                        ClcSnapshot.STATS_SNAPSHOT_CREATE,
                        1)
                    result.append(res)
            changed_servers = [
                server.id for server in servers_to_change if server.id]
            return changed, result, changed_servers
        except CLCException as ex:
            return self.module.fail_json(
                msg='Failed to create snap shot with Error : %s' % (ex))

    def ensure_server_snapshot_absent(self, server_ids):
        result = []
        changed = False
        try:
            servers = self._get_servers_from_clc(
                server_ids,
                'Failed to obtain server list from the CLC API')
            servers_to_change = [
                server for server in servers if len(
                    server.GetSnapshots()) > 0]
            for server in servers_to_change:
                changed = True
                if not self.module.check_mode:
                    res = server.DeleteSnapshot()
                    ClcSnapshot._push_metric(
                        ClcSnapshot.STATS_SNAPSHOT_CREATE,
                        1)
                    result.append(res)
            changed_servers = [
                server.id for server in servers_to_change if server.id]
            return changed, result, changed_servers
        except CLCException as ex:
            return self.module.fail_json(
                msg='Failed to delete snap shot with Error : %s' % (ex))

    def ensure_server_snapshot_restore(self, server_ids):
        result = []
        changed = False
        try:
            servers = self._get_servers_from_clc(
                server_ids,
                'Failed to obtain server list from the CLC API')
            servers_to_change = [
                server for server in servers if len(
                    server.GetSnapshots()) > 0]
            for server in servers_to_change:
                changed = True
                if not self.module.check_mode:
                    res = server.RestoreSnapshot()
                    ClcSnapshot._push_metric(
                        ClcSnapshot.STATS_SNAPSHOT_CREATE,
                        1)
                    result.append(res)
            changed_servers = [
                server.id for server in servers_to_change if server.id]
            return changed, result, changed_servers
        except CLCException as ex:
            return self.module.fail_json(
                msg='Failed to restore snap shot with Error : %s' % (ex))

    def _wait_for_requests_to_complete(self, requests_lst, action='create'):
        if self.module.params['wait']:
            for request in requests_lst:
                request.WaitUntilComplete()
                for request_details in request.requests:
                    if request_details.Status() != 'succeeded':
                        self.module.fail_json(
                            msg='Unable to process server snapshot request')

    @staticmethod
    def define_argument_spec():
        """
        This function defnines the dictionary object required for
        package module
        :return: the package dictionary object
        """
        argument_spec = dict(
            server_ids=dict(type='list', required=True),
            expiration_days=dict(default=7),
            wait=dict(default=True),
            state=dict(
                default='present',
                choices=[
                    'present',
                    'absent',
                    'restore']),
        )
        return argument_spec

    def _get_servers_from_clc(self, server_list, message):
        """
        Internal function to fetch list of CLC server objects from a list of server ids
        :param the list server ids
        :return the list of CLC server objects
        """
        try:
            return self.clc.v2.Servers(server_list).servers
        except CLCException as ex:
            return self.module.fail_json(msg=message + ': %s' % ex)

    def _set_clc_credentials_from_env(self):
        """
        Set the CLC Credentials on the sdk by reading environment variables
        :return: none
        """
        env = os.environ
        v2_api_token = env.get('CLC_V2_API_TOKEN', False)
        v2_api_username = env.get('CLC_V2_API_USERNAME', False)
        v2_api_passwd = env.get('CLC_V2_API_PASSWD', False)
        clc_alias = env.get('CLC_ACCT_ALIAS', False)
        api_url = env.get('CLC_V2_API_URL', False)

        if api_url:
            self.clc.defaults.ENDPOINT_URL_V2 = api_url

        if v2_api_token and clc_alias:
            self.clc._LOGIN_TOKEN_V2 = v2_api_token
            self.clc._V2_ENABLED = True
            self.clc.ALIAS = clc_alias
        elif v2_api_username and v2_api_passwd:
            self.clc.v2.SetCredentials(
                api_username=v2_api_username,
                api_passwd=v2_api_passwd)
        else:
            return self.module.fail_json(
                msg="You must set the CLC_V2_API_USERNAME and CLC_V2_API_PASSWD "
                    "environment variables")

    @staticmethod
    def _push_metric(path, count):
        try:
            sock = socket.socket()
            sock.settimeout(ClcSnapshot.SOCKET_CONNECTION_TIMEOUT)
            sock.connect((ClcSnapshot.STATSD_HOST, ClcSnapshot.STATSD_PORT))
            sock.sendall('%s %s %d\n' % (path, count, int(time.time())))
            sock.close()
        except socket.gaierror:
            # do nothing, ignore and move forward
            error = ''
        except socket.error:
            # nothing, ignore and move forward
            error = ''


def main():
    """
    Main function
    :return: None
    """
    module = AnsibleModule(
        argument_spec=ClcSnapshot.define_argument_spec(),
        supports_check_mode=True
    )
    clc_snapshot = ClcSnapshot(module)
    clc_snapshot.process_request()

from ansible.module_utils.basic import *
if __name__ == '__main__':
    main()
