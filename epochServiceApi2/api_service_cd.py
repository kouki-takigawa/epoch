#   Copyright 2021 NEC Corporation
#
#   Licensed under the Apache License, Version 2.0 (the "License");
#   you may not use this file except in compliance with the License.
#   You may obtain a copy of the License at
#
#       http://www.apache.org/licenses/LICENSE-2.0
#
#   Unless required by applicable law or agreed to in writing, software
#   distributed under the License is distributed on an "AS IS" BASIS,
#   WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
#   See the License for the specific language governing permissions and
#   limitations under the License.

from flask import Flask, request, abort, jsonify, render_template
from datetime import datetime
import inspect
import os
import json
import tempfile
import subprocess
import time
import re
from urllib.parse import urlparse
import base64
import requests
from requests.auth import HTTPBasicAuth
import traceback
from datetime import timedelta, timezone

import globals
import common
import const
import multi_lang
import api_service_current

# 設定ファイル読み込み・globals初期化
app = Flask(__name__)
app.config.from_envvar('CONFIG_API_SERVICE_PATH')
globals.init(app)


# 共通項目
column_indexes_common = {
    "method": 0,    # 実行処理種別
    "delete": 1,    # 廃止
    "record_no": 2, # No
}

# 項目名リスト
column_names_opelist = {
    'operation_id': 'オペレーションID',
    'operation_name': 'オペレーション名',
    'operation_date': '実施予定日時',
    'remarks': '備考',
}

COND_CLASS_NO_CD_EXEC = 2


def post_cd_pipeline(workspace_id):
    """CDパイプライン情報設定

    Args:
        workspace_id (int): workspace ID

    Returns:
        Response: HTTP Respose
    """

    app_name = "ワークスペース情報:"
    exec_stat = "CDパイプライン情報設定"
    error_detail = ""

    try:
        globals.logger.debug('#' * 50)
        globals.logger.debug('CALL {}'.format(inspect.currentframe().f_code.co_name))
        globals.logger.debug('#' * 50)


        # ヘッダ情報
        post_headers = {
            'Content-Type': 'application/json',
        }

        # 引数をJSON形式で受け取りそのまま引数に設定
        # post_data = request.json.copy()
        # workspace get
        api_url = "{}://{}:{}/workspace/{}".format(os.environ['EPOCH_RS_WORKSPACE_PROTOCOL'],
                                                    os.environ['EPOCH_RS_WORKSPACE_HOST'],
                                                    os.environ['EPOCH_RS_WORKSPACE_PORT'],
                                                    workspace_id)
        response = requests.get(api_url)

        if response.status_code != 200:
            error_detail = multi_lang.get_text("EP020-0013", "ワークスペース情報の取得に失敗しました")
            globals.logger.debug(error_detail)
            raise common.UserException(error_detail)

        # 取得したワークスペース情報を退避 Save the acquired workspace information
        ret = json.loads(response.text)
        # 取得したworkspace情報をパラメータとして受け渡す Pass the acquired workspace information as a parameter
        post_data = ret["rows"][0]

        # ワークスペース状態の取得 Get workspace status
        api_url = "{}://{}:{}/workspace/{}/status".format(os.environ['EPOCH_RS_WORKSPACE_PROTOCOL'],
                                                    os.environ['EPOCH_RS_WORKSPACE_HOST'],
                                                    os.environ['EPOCH_RS_WORKSPACE_PORT'],
                                                    workspace_id)
        response = requests.get(api_url)

        if response.status_code != 200:
            error_detail = multi_lang.get_text("EP020-0026", "ワークスペース状態情報の取得に失敗しました")
            globals.logger.debug(error_detail)
            raise common.UserException(error_detail)

        # 取得したワークスペース状態を退避 Save the acquired workspace status
        get_workspace_status = json.loads(response.text)
        # 更新で使用する項目のみを展開する Expand only the items used in the update
        workspace_status = {
            const.STATUS_CD_SETTING : get_workspace_status[const.STATUS_CD_SETTING] 
        }

        # 前回の結果が正常終了しているかチェックする
        # Be sure to execute CD settings except OK
        if workspace_status[const.STATUS_CD_SETTING] == const.STATUS_OK:

            # 更新前ワークスペース情報取得 Get workspace before update
            api_url = "{}://{}:{}/workspace/{}/before".format(os.environ['EPOCH_RS_WORKSPACE_PROTOCOL'],
                                                        os.environ['EPOCH_RS_WORKSPACE_HOST'],
                                                        os.environ['EPOCH_RS_WORKSPACE_PORT'],
                                                        workspace_id)
            response = requests.get(api_url)

            if response.status_code == 200:
                # 取得したワークスペース情報を退避 Save the acquired workspace information
                ret = json.loads(response.text)
                # 取得したworkspace情報をパラメータとして受け渡す Pass the acquired workspace information as a parameter
                before_data = ret["rows"][0]
            elif response.status_code == 404:
                before_data = None
            elif response.status_code != 200:
                error_detail = multi_lang.get_text("EP020-0013", "ワークスペース情報の取得に失敗しました")
                globals.logger.debug(error_detail)
                raise common.UserException(error_detail)
        else:
            # OK以外は、必ずCD設定を実行
            # Be sure to execute CD settings except OK
            before_data = None

        cd_config_json_after = post_data["cd_config"].copy()
        if before_data is not None:
            cd_config_json_before = before_data["cd_config"].copy()
        # cd_exec_usersの情報は比較に必要ないのでJsonから削除（環境毎）
        # Since the information of cd_exec_users is not necessary for comparison, it is deleted from Json (for each environment)
        for (env_idx, env) in enumerate(cd_config_json_after["environments"]):
            # 要素があれば削除
            if "cd_exec_users" in env:
                cd_config_json_after["environments"][env_idx].pop("cd_exec_users")

        if before_data is not None:
            for (env_idx, env) in enumerate(cd_config_json_before["environments"]):
                # 要素があれば削除
                if "cd_exec_users" in env:
                    cd_config_json_before["environments"][env_idx].pop("cd_exec_users")

        cd_config_str_after = json.dumps(cd_config_json_after)
        if before_data is not None:
            cd_config_str_before = json.dumps(cd_config_json_before)
        else:
            cd_config_str_before = None

        # 更新前、更新後が一致しない場合にCIパイプラインの設定を行なう
        # Set up the CI pipeline when the pre-update and post-update do not match
        if cd_config_str_after != cd_config_str_before:
            globals.logger.debug("changed cd_config parameter!")

            # 実行前はNGで更新 Update with NG before execution
            workspace_status[const.STATUS_CD_SETTING] = const.STATUS_NG
            # workspace 状態更新 workspace status update
            api_url = "{}://{}:{}/workspace/{}/status".format(os.environ['EPOCH_RS_WORKSPACE_PROTOCOL'],
                                                                os.environ['EPOCH_RS_WORKSPACE_HOST'],
                                                                os.environ['EPOCH_RS_WORKSPACE_PORT'],
                                                                workspace_id)

            response = requests.put(api_url, headers=post_headers, data=json.dumps(workspace_status))

            if response.status_code != 200:
                error_detail = multi_lang.get_text("EP020-0027", "ワークスペース状態情報の更新に失敗しました")
                globals.logger.debug(error_detail)
                raise common.UserException(error_detail)

            # Automatic generation of IaC repository - IaCリポジトリの自動生成
            exec_stat = "CDパイプライン情報設定(IaCリポジトリ生成)"

            # epoch-control-inside-gitlab-api の呼び先設定
            api_url_gitlab = "{}://{}:{}/workspace/{}/gitlab".format(os.environ["EPOCH_CONTROL_INSIDE_GITLAB_PROTOCOL"], 
                                                                    os.environ["EPOCH_CONTROL_INSIDE_GITLAB_HOST"], 
                                                                    os.environ["EPOCH_CONTROL_INSIDE_GITLAB_PORT"],
                                                                    workspace_id)

            git_projects = []
            if post_data['cd_config']['environments_common']['git_repositry']['housing'] == 'inner':
                for pipeline_iac in post_data['cd_config']['environments']:
                    ap_data = {
                        'git_repositry': {
                            'user': post_data['cd_config']['environments_common']['git_repositry']['user'],
                            'token': post_data['cd_config']['environments_common']['git_repositry']['token'],
                            'url': pipeline_iac['git_repositry']['url'],
                        }
                    }
                    git_projects.append(ap_data)

            for proj_data in git_projects:
                # gitlab/repos post送信
                response = requests.post('{}/repos'.format(api_url_gitlab), headers=post_headers, data=json.dumps(proj_data))
                globals.logger.debug("post gitlab/repos response:{}".format(response.text))

                if response.status_code != 200 and response.status_code != 201:
                    error_detail = 'gitlab/repos post処理に失敗しました'
                    raise common.UserException(error_detail)


            exec_stat = "CDパイプライン情報設定(ITA - Git環境情報設定)"

            # epoch-control-ita-api の呼び先設定
            api_url = "{}://{}:{}/workspace/{}/it-automation/manifest/git".format(os.environ['EPOCH_CONTROL_ITA_PROTOCOL'],
                                                                                os.environ['EPOCH_CONTROL_ITA_HOST'],
                                                                                os.environ['EPOCH_CONTROL_ITA_PORT'],
                                                                                workspace_id)

            # パイプライン設定(ITA - Git環境情報設定)
            response = requests.post( api_url, headers=post_headers, data=json.dumps(post_data))
            globals.logger.debug("it-automation/manifest/git:response:" + response.text)
            if response.status_code != 200 and response.status_code != 201:
                if common.is_json_format(response.text):
                    ret = json.loads(response.text)
                    globals.logger.debug(ret["result"])
                    if "errorDetail" in ret:
                        exec_detail = ret["errorDetail"]
                    else:
                        exec_detail = ""
                    raise common.UserException(exec_detail)
                else:
                    globals.logger.debug(response.text)
                    error_detail = 'it-automation/manifest/git post処理に失敗しました'
                    raise common.UserException(error_detail)

            exec_stat = "CDパイプライン情報設定(ArgoCD設定)"
            # epoch-control-argocd-api の呼び先設定
            api_url = "{}://{}:{}/workspace/{}/argocd/settings".format(os.environ['EPOCH_CONTROL_ARGOCD_PROTOCOL'],
                                                                        os.environ['EPOCH_CONTROL_ARGOCD_HOST'],
                                                                        os.environ['EPOCH_CONTROL_ARGOCD_PORT'],
                                                                        workspace_id)
            # argocd/settings post送信
            response = requests.post(api_url, headers=post_headers, data=json.dumps(post_data))
            globals.logger.debug("post argocd/settings response:{}".format(response.text))

            if response.status_code != 200:
                error_detail = 'argocd/settings post処理に失敗しました'
                raise common.UserException(error_detail)

            # 実行後はOKで更新 Update with OK after execution
            workspace_status[const.STATUS_CD_SETTING] = const.STATUS_OK
            globals.logger.debug("workspace_status:{}".format(workspace_status))
            # workspace 状態更新 workspace status update
            api_url = "{}://{}:{}/workspace/{}/status".format(os.environ['EPOCH_RS_WORKSPACE_PROTOCOL'],
                                                                os.environ['EPOCH_RS_WORKSPACE_HOST'],
                                                                os.environ['EPOCH_RS_WORKSPACE_PORT'],
                                                                workspace_id)

            response = requests.put(api_url, headers=post_headers, data=json.dumps(workspace_status))

            if response.status_code != 200:
                error_detail = multi_lang.get_text("EP020-0027", "ワークスペース状態情報の更新に失敗しました")
                globals.logger.debug(error_detail)
                raise common.UserException(error_detail)

        ret_status = 200

        # 戻り値をそのまま返却        
        return jsonify({"result": ret_status}), ret_status

    except common.UserException as e:
        return common.server_error_to_message(e, app_name + exec_stat, error_detail)
    except Exception as e:
        return common.server_error_to_message(e, app_name + exec_stat, error_detail)


def get_cd_pipeline_argocd(workspace_id):
    """Get CD pipeline (ArgoCD) information - CDパイプライン(ArgoCD)情報取得

    Args:
        workspace_id (int): workspace ID

    Returns:
        Response: HTTP Respose
    """

    app_name = multi_lang.get_text("EP020-0034", "CD実行結果(ArgoCD):") 
    exec_stat = multi_lang.get_text("EP020-0030", "CDパイプライン(ArgoCD)情報取得")
    error_detail = ""

    try:
        globals.logger.debug('#' * 50)
        globals.logger.debug('CALL {}'.format(inspect.currentframe().f_code.co_name))
        globals.logger.debug('#' * 50)

        # CD結果の全件を取得する
        api_url = "{}://{}:{}/workspace/{}/cd/result".format(os.environ['EPOCH_RS_CD_RESULT_PROTOCOL'],
                                                        os.environ['EPOCH_RS_CD_RESULT_HOST'],
                                                        os.environ['EPOCH_RS_CD_RESULT_PORT'],
                                                        workspace_id)
        response = requests.get(api_url)

        if response.status_code != 200:
            error_detail = multi_lang.get_text("EP020-0032", "CDパイプライン(ArgoCD)情報の取得に失敗しました")
            globals.logger.debug(error_detail)
            raise common.UserException(error_detail)

        res_json = json.loads(response.text)

        ret_status = res_json["result"]
        
        rows = []
        for data_row in res_json["rows"]:
            row = data_row
            # 内容はjson型なので変換して受け渡す
            # Since the content is json type, convert and pass
            row["contents"] = json.loads(data_row["contents"])
            argocd_result = row["contents"]["argocd_results"]            
            
            resource_status = []
            # Format a part of the result JSON (resource_status) - 結果JSONの一部（resource_status）を整形
            for status_resources in argocd_result["result"]["status"]["resources"]:
                for sync_result_resources in argocd_result["result"]["status"]["operationState"]["syncResult"]["resources"]:
                    
                    if str(status_resources["kind"]) == str(sync_result_resources["kind"]) \
                    and str(status_resources["name"]) == str(sync_result_resources["name"]): 
                        # "kind", "name" merge resource information with the same name 
                        # "kind", "name"が同名のリソース情報をマージ
                        resource_status.append(
                            {
                                "kind": status_resources["kind"],
                                "name": status_resources["name"],
                                "health_status": status_resources["health"]["status"],
                                "sync_status": sync_result_resources["status"],
                                "message": sync_result_resources["message"]
                            }
                        )

            # Format the entire result JSON - 結果JSONの全体を整形
            rows.append(
                {
                    "trace_id": row["contents"]["trace_id"],
                    "environment_name": argocd_result["result"]["metadata"]["name"],
                    "namespace": argocd_result["result"]["metadata"]["namespace"],
                    "health": {
                        "status": argocd_result["result"]["status"]["health"]["status"]
                    },
                    "sync_status": {
                        "status": argocd_result["result"]["status"]["sync"]["status"],
                        "repo_url": argocd_result["result"]["status"]["sync"]["comparedTo"]["source"]["repoURL"],
                        "server": argocd_result["result"]["status"]["sync"]["comparedTo"]["destination"]["server"],
                        "revision": argocd_result["result"]["status"]["sync"]["revision"]                        },
                    "resource_status": resource_status,
                    "startedAt": argocd_result["result"]["status"]["operationState"]["startedAt"],
                    "finishedAt": argocd_result["result"]["status"]["operationState"]["finishedAt"]
                }
            )
            
        # 戻り値をそのまま返却 Return the return value as it is       
        return jsonify({"result": ret_status, "rows": rows}), ret_status

    except common.UserException as e:
        return common.server_error_to_message(e, app_name + exec_stat, error_detail)
    except Exception as e:
        return common.server_error_to_message(e, app_name + exec_stat, error_detail)


def post_cd_pipeline_argocd_sync(workspace_id):
    """Get CD pipeline (ArgoCD) information - CDパイプライン(ArgoCD)情報取得

    Args:
        workspace_id (int): workspace ID

    Returns:
        Response: HTTP Respose
    """

    app_name = multi_lang.get_text("EP020-0034", "CD実行結果(ArgoCD):") 
    exec_stat = multi_lang.get_text("EP020-0031", "CDパイプライン(ArgoCD)同期実行")
    error_detail = ""

    try:
        globals.logger.debug('#' * 50)
        globals.logger.debug('CALL {} workspace_id[{}]'.format(inspect.currentframe().f_code.co_name, workspace_id))
        globals.logger.debug('#' * 50)

        # ヘッダ情報
        post_headers = {
            'Content-Type': 'application/json',
        }

        # 状態をArgoCD同期中に変更
        req_json = request.json.copy()
        environment_name = req_json["environment_name"]

        # ArgoCD Sync call 
        api_url = "{}://{}:{}/workspace/{}/argocd/app/{}/sync".format(os.environ['EPOCH_CONTROL_ARGOCD_PROTOCOL'],
                                                os.environ['EPOCH_CONTROL_ARGOCD_HOST'],
                                                os.environ['EPOCH_CONTROL_ARGOCD_PORT'],
                                                workspace_id,
                                                environment_name)
        response = requests.post(api_url, headers=post_headers)

        if response.status_code != 200:
            error_detail = multi_lang.get_text("EP020-0033", "CDパイプライン(ArgoCD)同期実行に失敗しました")
            globals.logger.debug(error_detail)
            raise common.UserException(error_detail)

        ret_status = 200

        # 戻り値をそのまま返却        
        return jsonify({"result": ret_status}), ret_status

    except common.UserException as e:
        return common.server_error_to_message(e, app_name + exec_stat, error_detail)
    except Exception as e:
        return common.server_error_to_message(e, app_name + exec_stat, error_detail)


def cd_execute(workspace_id):
    """CD実行 cd execute

    Args:
        workspace_id (int): workspace ID

    Returns:
        Response: HTTP Respose
    """

    app_name = multi_lang.get_text("EP020-0003", "ワークスペース情報:")
    exec_stat = multi_lang.get_text("EP020-0019", "CD実行")
    error_detail = ""

    try:
        globals.logger.debug('#' * 50)
        globals.logger.debug('CALL {}'.format(inspect.currentframe().f_code.co_name))
        globals.logger.debug('#' * 50)

        # 引数をJSON形式で受け取りそのまま引数に設定 parameter set json
        request_json = request.json.copy()

        # ユーザIDの取得 get user id
        user_id = common.get_current_user(request.headers)

        # CD実行権限があるかチェックする Check if you have CD execution permission
        check_role = const.ROLE_WS_ROLE_CD_EXECUTE[0].format(workspace_id)

        # 取得したユーザーのロールを取得 Get the role of the acquired user
        api_url = "{}://{}:{}/{}/user/{}/roles/epoch-system".format(os.environ['EPOCH_EPAI_API_PROTOCOL'],
                                                                os.environ['EPOCH_EPAI_API_HOST'],
                                                                os.environ['EPOCH_EPAI_API_PORT'],
                                                                os.environ["EPOCH_EPAI_REALM_NAME"],
                                                                user_id
                                                        )

        #
        # get user role - ユーザーロール情報取得
        #
        response = requests.get(api_url)
        if response.status_code != 200:
            error_detail = multi_lang.get_text("EP020-0009", "ユーザーロール情報の取得に失敗しました")
            globals.logger.debug(error_detail)
            raise common.UserException("{} Error user role get status:{}".format(inspect.currentframe().f_code.co_name, response.status_code))

        ret_roles = json.loads(response.text)
        # globals.logger.debug(f"roles:{ret_roles}")

        exist_role = False
        # 取得したすべてのロールにCD実行があるかチェックする Check if all the retrieved roles have a CD run
        for get_role in ret_roles["rows"]:
            # globals.logger.debug('role:{}'.format(get_role["name"]))
            # ロールがあればチェックOK Check OK if there is a roll
            if get_role["name"] == check_role:
                exist_role = True
                break

        # 権限がない場合はエラーとする If you do not have permission, an error will occur.
        if not exist_role:
            error_detail = multi_lang.get_text("EP020-0020", "CD実行権限がありません")
            globals.logger.debug(error_detail)
            raise common.AuthException(error_detail)


        # workspace GET送信 workspace get
        api_url = "{}://{}:{}/workspace/{}".format(os.environ['EPOCH_RS_WORKSPACE_PROTOCOL'],
                                                    os.environ['EPOCH_RS_WORKSPACE_HOST'],
                                                    os.environ['EPOCH_RS_WORKSPACE_PORT'],
                                                    workspace_id)
        response = requests.get(api_url)

        # 取得できなかった場合は、終了する If it cannot be obtained, it will end.
        if response.status_code != 200:
            error_detail = multi_lang.get_text("EP020-0013", "ワークスペース情報の取得に失敗しました")
            globals.logger.debug(error_detail)
            raise common.UserException("{} Error workspace info get status:{}".format(inspect.currentframe().f_code.co_name, response.status_code))

        # 取得したJSON結果が正常でない場合、例外を返す If the JSON result obtained is not normal, an exception will be returned.
        ret = json.loads(response.text)
        workspace_info = ret["rows"][0]

        dest_namespace = ""
        # workspace情報のCD実行権限があるかチェックする Check if you have CD execution permission for workspace information
        found_user = False
        # 環境情報がない場合も考慮 Consider even if there is no environmental information
        if "environments" in workspace_info["cd_config"]:
            # 選択された環境と一致するまで環境情報をすべて処理する Process all environment information until it matches the selected environment
            for env in workspace_info["cd_config"]["environments"]:
                # 実行環境に該当する情報のユーザーIDを取得する Acquire the user ID of the information corresponding to the execution environment
                if env["name"] == request_json["environmentName"]:
                    dest_namespace = env["deploy_destination"]["namespace"]
                    # CD実行権限ありの人すべての場合は、OKとする OK for all people with CD execution permission
                    if env["cd_exec_users"]["user_select"] == "all":
                        found_user = True
                        break
                    # 選択肢の場合は、該当するユーザーがあるかどうかチェックする If it's an option, check if there is a suitable user
                    elif user_id in env["cd_exec_users"]["user_id"]:
                        found_user = True
                        break

        # 最終的に実行可能かチェックする Check if it is finally feasible
        if not found_user:
            error_detail = multi_lang.get_text("EP020-0020", "CD実行権限がありません")
            globals.logger.debug(error_detail)
            raise common.AuthException(error_detail)

        api_url = "{}://{}:{}/{}/user/{}".format(os.environ['EPOCH_EPAI_API_PROTOCOL'],
                                                os.environ['EPOCH_EPAI_API_HOST'],
                                                os.environ['EPOCH_EPAI_API_PORT'],
                                                os.environ["EPOCH_EPAI_REALM_NAME"],
                                                user_id
                                            )
        #
        # get users - ユーザー取得
        #
        response = requests.get(api_url)
        if response.status_code != 200 and response.status_code != 404:
            error_detail = multi_lang.get_text("EP020-0008", "ユーザー情報の取得に失敗しました")
            raise common.UserException("{} Error user get status:{}".format(inspect.currentframe().f_code.co_name, response.status_code))

        users = json.loads(response.text)
        globals.logger.debug(f"users:{users}")

        # ヘッダ情報 header info.
        post_headers = {
            'Content-Type': 'application/json',
        }

        # 呼び出すapiInfoは環境変数より取得 api url set
        apiInfo = "{}://{}:{}/workspace/{}/it-automation".format(os.environ["EPOCH_CONTROL_ITA_PROTOCOL"],
                                                                os.environ["EPOCH_CONTROL_ITA_HOST"],
                                                                os.environ["EPOCH_CONTROL_ITA_PORT"],
                                                                workspace_id)
        # globals.logger.debug ("cicd url:" + apiInfo)

        # オペレーション一覧の取得(ITA) get a ita operations
        request_response = requests.get(apiInfo + "/cd/operations", headers=post_headers)
        # globals.logger.debug("cd/operations:" + request_response.text)
        # 戻り値がJson形式かチェックする return parameter is json?
        if common.is_json_format(request_response.text):
            ret = json.loads(request_response.text)
        else:
            globals.logger.debug("cd/operations:response:{}".format(request_response.text))
            error_detail = multi_lang.get_text("EP020-0021", "CD実行に失敗しました")
            raise common.UserException(error_detail)

        ret_ita = ret['rows']
        # 項目位置の取得 get columns 
        column_indexes_opelist = column_indexes(column_names_opelist, ret_ita['resultdata']['CONTENTS']['BODY'][0])
        globals.logger.debug('---- Operation Index ----')
        globals.logger.debug(column_indexes_opelist)

        # 引数のgit urlをもとにオペレーションIDを取得 get operation id for git-url
        ope_id = search_opration_id(ret_ita['resultdata']['CONTENTS']['BODY'], column_indexes_opelist, request_json['operationSearchKey'])
        if ope_id is None:
            globals.logger.debug("Operation ID Not found!")
            error_detail = "Operation ID Not found!"
            raise common.UserException(error_detail)

        # CD実行の引数を設定 paramater of cd execute 
        post_data = {
            "operation_id" : ope_id,
            "conductor_class_no" : COND_CLASS_NO_CD_EXEC,
            "preserve_datetime" : request_json["preserveDatetime"]
        }
        post_data = json.dumps(post_data)

        # CD実行(ITA) cd execute ita
        response = requests.post(apiInfo + "/cd/execute", headers=post_headers, data=post_data)
        # 正常終了したか確認 Check if it ended normally
        if response.status_code != 200:  
            globals.logger.debug("status error: ita/execute:response:{}".format(response.text))
            error_detail = multi_lang.get_text("EP020-0028", "CD実行に失敗しました")
            raise common.UserException(error_detail)

        # 戻り値をjson形式に変換 Convert return value to json format
        ita_ret = json.loads(response.text)

        # CD実行結果を登録する Register the CD execution result
        trace_id = "{0:010}".format(int(ita_ret["cd_result_id"]))
        post_data = {
            "trace_id": trace_id,
            "cd_status": const.CD_STATUS_START,
            "environment_name": request_json["environmentName"],
            "namespace": dest_namespace,
            "workspace_info": workspace_info,
            "ita_results": {
            },
            "argocd_results": {
            },
        }

        api_url = "{}://{}:{}/workspace/{}/member/{}/cd/result/{}".format(os.environ['EPOCH_RS_CD_RESULT_PROTOCOL'],
                                                    os.environ['EPOCH_RS_CD_RESULT_HOST'],
                                                    os.environ['EPOCH_RS_CD_RESULT_PORT'],
                                                    workspace_id,
                                                    users["info"]["username"],
                                                    trace_id
                                                    )

        response = requests.post(api_url, headers=post_headers, data=json.dumps(post_data))
        if response.status_code != 200:
            error_detail = multi_lang.get_text("EP020-0029", "CD実行結果の登録に失敗しました")
            globals.logger.debug(error_detail)
            raise common.UserException("{} Error cd result registration status:{}".format(inspect.currentframe().f_code.co_name, response.status_code))


        #
        # logs output - ログ出力
        #
        post_data = {
            "action" : "cd execute",
            "cd_execute_contents": post_data,
            "cd_execute_user": users["info"]["username"],
        }

        api_url = "{}://{}:{}/workspace/{}/member/{}/logs/{}".format(os.environ['EPOCH_RS_LOGS_PROTOCOL'],
                                                    os.environ['EPOCH_RS_LOGS_HOST'],
                                                    os.environ['EPOCH_RS_LOGS_PORT'],
                                                    workspace_id,
                                                    users["info"]["username"],
                                                    const.LOG_KIND_UPDATE
                                                    )

        response = requests.post(api_url, headers=post_headers, data=json.dumps(post_data))
        if response.status_code != 200:
            error_detail = multi_lang.get_text("EP020-0023", "ログ出力に失敗しました")
            globals.logger.debug(error_detail)
            raise common.UserException("{} Error log output status:{}".format(inspect.currentframe().f_code.co_name, response.status_code))

        # 正常終了 normal return code
        ret_status = 200

        return jsonify({"result": ret_status}), ret_status

    except common.AuthException as e:
        return jsonify({"result": 401, "errorDetail": error_detail}), 401
    except common.UserException as e:
        return common.server_error_to_message(e, app_name + exec_stat, error_detail)
    except Exception as e:
        return common.server_error_to_message(e, app_name + exec_stat, error_detail)


def search_opration_id(opelist, column_indexes, git_url):
    """オペレーションの検索

    Args:
        opelist (dict): Operation list
        column_indexes (dict): column indexes
        git_url (str): git url

    Returns:
        str: operation id
    """
    for idx, row in enumerate(opelist):
        if idx == 0:
            # 1行目はヘッダなので読み飛ばし
            continue

        if row[column_indexes_common["delete"]] != "":
            # 削除は無視
            continue

        if row[column_indexes['remarks']] is None:
            # 備考設定なしは無視
            continue

        globals.logger.debug('git_url:'+git_url)
        globals.logger.debug('row[column_indexes[remarks]]:'+row[column_indexes['remarks']])
        if git_url == row[column_indexes['remarks']]:
            # 備考にgit_urlが含まれているとき
            globals.logger.debug('find:' + str(idx))
            return row[column_indexes['operation_id']]

    # 存在しないとき
    return None

def column_indexes(column_names, row_header):
    """項目位置の取得

    Args:
        column_names (str): column name
        row_header (dict): row header info.

    Returns:
        [type]: [description]
    """
    column_indexes = {}
    for idx in column_names:
        column_indexes[idx] = row_header.index(column_names[idx])
    return column_indexes

def cd_environment_get(workspace_id):
    """CD実行環境取得 cd execute environment get

    Args:
        workspace_id (int): workspace ID

    Returns:
        Response: HTTP Respose
    """

    app_name = multi_lang.get_text("EP020-0022", "CD実行環境取得:")
    exec_stat = multi_lang.get_text("EP020-0017", "取得")
    error_detail = ""

    try:

        # ユーザIDの取得 get user id
        user_id = common.get_current_user(request.headers)

        # workspace GET送信 workspace get
        api_url = "{}://{}:{}/workspace/{}".format(os.environ['EPOCH_RS_WORKSPACE_PROTOCOL'],
                                                    os.environ['EPOCH_RS_WORKSPACE_HOST'],
                                                    os.environ['EPOCH_RS_WORKSPACE_PORT'],
                                                    workspace_id)
        response = requests.get(api_url)

        # 取得できなかった場合は、終了する If it cannot be obtained, it will end.
        if response.status_code != 200:
            error_detail = multi_lang.get_text("EP020-0013", "ワークスペース情報の取得に失敗しました")
            raise common.UserException("{} Error workspace info get status:{}".format(inspect.currentframe().f_code.co_name, response.status_code))

        # 取得したJSON結果が正常でない場合、例外を返す If the JSON result obtained is not normal, an exception will be returned.
        ret = json.loads(response.text)
        rows = ret["rows"]

        # workspace情報のCD実行権限がある環境情報のみ返却する Only the environment information for which you have the CD execution permission for workspace information is returned.
        ret_environments = []

        globals.logger.debug("cd_config:{}".format(rows[0]["cd_config"]))

        # 環境情報がない場合も考慮 Consider even if there is no environmental information
        if "environments" in rows[0]["cd_config"]:
            # 環境情報をすべて処理する Process all environmental information
            for env in rows[0]["cd_config"]["environments"]:
                globals.logger.debug("env:{}".format(env))
                # CD実行権限ありの人すべてまたはCD実行権限有の場合に環境を返却する Return the environment to all people with CD execution permission or if you have CD execution permission
                if env["cd_exec_users"]["user_select"] == "all" or \
                    user_id in env["cd_exec_users"]["user_id"]:

                    globals.logger.debug("HIT!!!!")
                    environment = {
                        "id": env["environment_id"],
                        "name": env["name"],
                    }
                    ret_environments.append(environment)

        # 正常終了 normal return code
        ret_status = 200

        return jsonify({"result": ret_status, "environments": ret_environments}), ret_status

    except common.UserException as e:
        return common.server_error_to_message(e, app_name + exec_stat, error_detail)
    except Exception as e:
        return common.server_error_to_message(e, app_name + exec_stat, error_detail)
