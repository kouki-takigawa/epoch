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
import hashlib

import globals
import common
import api_access_info

# 設定ファイル読み込み・globals初期化 flask setting file read and globals initialize
app = Flask(__name__)
app.config.from_envvar('CONFIG_API_ITA_PATH')
globals.init(app)

EPOCH_ITA_HOST = "it-automation"
EPOCH_ITA_PORT = "8084"

#
# メニューID
#
# 基本コンソール - 投入オペレーション一覧
ite_menu_operation = '2100000304'
# マニフェスト変数管理 - マニフェスト環境パラメータ
ita_menu_manifest_param = '0000000004'
# マニフェスト変数管理 - マニフェスト登録先Git環境パラメータ
ita_menu_gitenv_param = '0000000005'
# Ansible共通 - テンプレート管理
ita_menu_manifest_template = '2100040704'

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
column_names_gitlist = {
    'host' : 'ホスト名',
    'operation_id' : 'オペレーション/ID',
    'operation' : 'オペレーション/オペレーション',
    'git_url' : 'パラメータ/Git URL',
    'git_user' : 'パラメータ/Git User',
    'git_password' : 'パラメータ/Git Password',
    'lastupdate' : '更新用の最終更新日時',
}
# 項目名リスト
column_names_manifest_param = {
    'host' : 'ホスト名',
    'operation_id' : 'オペレーション/ID',
    'operation' : 'オペレーション/オペレーション',
    'indexes' : '代入順序',
    'image' : 'パラメータ/固定パラメータ/image',
    'image_tag' : 'パラメータ/固定パラメータ/image_tag',
    'param01' : 'パラメータ/汎用パラメータ/param01',
    'param02' : 'パラメータ/汎用パラメータ/param02',
    'param03' : 'パラメータ/汎用パラメータ/param03',
    'param04' : 'パラメータ/汎用パラメータ/param04',
    'param05' : 'パラメータ/汎用パラメータ/param05',
    'param06' : 'パラメータ/汎用パラメータ/param06',
    'param07' : 'パラメータ/汎用パラメータ/param07',
    'param08' : 'パラメータ/汎用パラメータ/param08',
    'param09' : 'パラメータ/汎用パラメータ/param09',
    'param10' : 'パラメータ/汎用パラメータ/param10',
    'param11' : 'パラメータ/汎用パラメータ/param11',
    'param12' : 'パラメータ/汎用パラメータ/param12',
    'param13' : 'パラメータ/汎用パラメータ/param13',
    'param14' : 'パラメータ/汎用パラメータ/param14',
    'param15' : 'パラメータ/汎用パラメータ/param15',
    'param16' : 'パラメータ/汎用パラメータ/param16',
    'param17' : 'パラメータ/汎用パラメータ/param17',
    'param18' : 'パラメータ/汎用パラメータ/param18',
    'param19' : 'パラメータ/汎用パラメータ/param19',
    'param20' : 'パラメータ/汎用パラメータ/param20',
    'template_name' : 'パラメータ/固定パラメータ/template_name',
    'lastupdate' : '更新用の最終更新日時',
}

param_value_host="ita-worker"
param_value_method_entry='登録'
param_value_method_update='更新'
param_value_method_delete='廃止'
param_value_operation_date='2999/12/31 23:59'
param_value_operation_name_prefix='CD実行:'


def settings_git_environment(workspace_id):
    """git environment setting

    Args:
        workspace_id (int): workspace ID

    Returns:
        Response: HTTP Respose
    """

    app_name = "ワークスペース情報:"
    exec_stat = "IT-Automation git情報設定"
    error_detail = ""

    try:
        globals.logger.debug('#' * 50)
        globals.logger.debug('CALL {}'.format(inspect.currentframe().f_code.co_name))
        globals.logger.debug('#' * 50)

        # パラメータ情報(JSON形式) prameter save
        payload = request.json.copy()

        # ワークスペースアクセス情報取得
        access_info = api_access_info.get_access_info(workspace_id)

        # namespaceの取得
        namespace = common.get_namespace_name(workspace_id)

        ita_restapi_endpoint = "http://{}.{}.svc:{}/default/menu/07_rest_api_ver1.php".format(EPOCH_ITA_HOST, namespace, EPOCH_ITA_PORT)
        ita_user = access_info['ITA_USER']
        ita_pass = access_info['ITA_PASSWORD']

        # HTTPヘッダの生成
        filter_headers = {
            'host': EPOCH_ITA_HOST + ':' + EPOCH_ITA_PORT,
            'Content-Type': 'application/json',
            'Authorization': base64.b64encode((ita_user + ':' + ita_pass).encode()),
            'X-Command': 'FILTER',
        }

        edit_headers = {
            'host': EPOCH_ITA_HOST + ':' + EPOCH_ITA_PORT,
            'Content-Type': 'application/json',
            'Authorization': base64.b64encode((ita_user + ':' + ita_pass).encode()),
            'X-Command': 'EDIT',
        }

        #
        # オペレーションの取得
        #
        opelist_resp = requests.post(ita_restapi_endpoint + '?no=' + ite_menu_operation, headers=filter_headers)
        opelist_json = json.loads(opelist_resp.text)
        globals.logger.debug('---- Operation ----')
        #logger.debug(opelist_resp.text.encode().decode('unicode-escape'))
        # globals.logger.debug(opelist_resp.text)

        # 項目位置の取得
        column_indexes_opelist = column_indexes(column_names_opelist, opelist_json['resultdata']['CONTENTS']['BODY'][0])
        globals.logger.debug('---- Operation Index ----')
        # globals.logger.debug(column_indexes_opelist)

        #
        # オペレーションの追加処理
        #
        opelist_edit = []
        for idx_req, row_req in enumerate(payload['cd_config']['environments']):
            if search_opration(opelist_json['resultdata']['CONTENTS']['BODY'], column_indexes_opelist, row_req['git_repositry']['url']) == -1:
                # オペレーションになければ、追加データを設定
                opelist_edit.append(
                    {
                        str(column_indexes_common['method']) : param_value_method_entry,
                        str(column_indexes_opelist['operation_name']) : param_value_operation_name_prefix + row_req['git_repositry']['url'],
                        str(column_indexes_opelist['operation_date']) : param_value_operation_date,
                        str(column_indexes_opelist['remarks']) : row_req['git_repositry']['url'],
                    }
                )

        if len(opelist_edit) > 0:
            #
            # オペレーションの追加がある場合
            #
            ope_add_resp = requests.post(ita_restapi_endpoint + '?no=' + ite_menu_operation, headers=edit_headers, data=json.dumps(opelist_edit))

            globals.logger.debug('---- ope_add_resp ----')
            #logger.debug(ope_add_resp.text.encode().decode('unicode-escape'))
            globals.logger.debug(ope_add_resp.text)

            # 追加後再取得(オペレーションIDが決定する)
            opelist_resp = requests.post(ita_restapi_endpoint + '?no=' + ite_menu_operation, headers=filter_headers)        
            opelist_json = json.loads(opelist_resp.text)
            globals.logger.debug('---- Operation ----')
            #logger.debug(opelist_resp.text.encode().decode('unicode-escape'))

        #
        # Git環境情報の取得
        #
        gitlist_resp = requests.post(ita_restapi_endpoint + '?no=' + ita_menu_gitenv_param, headers=filter_headers)
        gitlist_json = json.loads(gitlist_resp.text)
        globals.logger.debug('---- Git Environments ----')
        #logger.debug(gitlist_resp.text.encode().decode('unicode-escape'))
        #logger.debug(gitlist_resp.text)

        # 項目位置の取得
        column_indexes_gitlist = column_indexes(column_names_gitlist, gitlist_json['resultdata']['CONTENTS']['BODY'][0])
        globals.logger.debug('---- Git Environments Index ----')
        # logger.debug(column_indexes_gitlist)

        # Responseデータの初期化
        response = {"items":[]}
        # Git環境情報の追加・更新
        gitlist_edit = []
        for idx_req, row_req in enumerate(payload['cd_config']['environments']):
            idx_git = search_gitlist(gitlist_json['resultdata']['CONTENTS']['BODY'], column_indexes_gitlist, row_req['git_repositry']['url'])
            if idx_git == -1:
                # リストになければ、追加データを設定
                # 追加対象のURLのオペレーション
                idx_ope = search_opration(opelist_json['resultdata']['CONTENTS']['BODY'], column_indexes_opelist, row_req['git_repositry']['url'])

                # 追加処理データの設定
                gitlist_edit.append(
                    {
                        str(column_indexes_common['method']) : param_value_method_entry,
                        str(column_indexes_gitlist['host']) : param_value_host,
                        str(column_indexes_gitlist['operation_id']) : opelist_json['resultdata']['CONTENTS']['BODY'][idx_ope][column_indexes_opelist['operation_id']],
                        str(column_indexes_gitlist['operation']) : format_opration_info(opelist_json['resultdata']['CONTENTS']['BODY'][idx_ope], column_indexes_opelist),
                        str(column_indexes_gitlist['git_url']) : row_req['git_repositry']['url'],
                        str(column_indexes_gitlist['git_user']) : payload['cd_config']['environments_common']['git_repositry']['user'],
                        str(column_indexes_gitlist['git_password']) : payload['cd_config']['environments_common']['git_repositry']['token'],
                    }
                )

                # レスポンスデータの設定
                response["items"].append(
                    {
                        'operation_id' : opelist_json['resultdata']['CONTENTS']['BODY'][idx_ope][column_indexes_opelist['operation_id']],
                        'git_url' : row_req['git_repositry']['url'],
                        'git_user' : payload['cd_config']['environments_common']['git_repositry']['user'],
                        'git_password' : payload['cd_config']['environments_common']['git_repositry']['token'],
                    }
                )

            else:
                # リストにあれば、更新データを設定
                gitlist_edit.append(
                    {
                        str(column_indexes_common['method']) : param_value_method_update,
                        str(column_indexes_common['record_no']) : gitlist_json['resultdata']['CONTENTS']['BODY'][idx_git][column_indexes_common['record_no']],
                        str(column_indexes_gitlist['host']) : gitlist_json['resultdata']['CONTENTS']['BODY'][idx_git][column_indexes_gitlist['host']],
                        str(column_indexes_gitlist['operation']) : gitlist_json['resultdata']['CONTENTS']['BODY'][idx_git][column_indexes_gitlist['operation']],
                        str(column_indexes_gitlist['git_url']) : row_req['git_repositry']['url'],
                        str(column_indexes_gitlist['git_user']) : payload['cd_config']['environments_common']['git_repositry']['user'],
                        str(column_indexes_gitlist['git_password']) : payload['cd_config']['environments_common']['git_repositry']['token'],
                        str(column_indexes_gitlist['lastupdate']) : gitlist_json['resultdata']['CONTENTS']['BODY'][idx_git][column_indexes_gitlist['lastupdate']],
                    }
                )

                # レスポンスデータの設定
                response["items"].append(
                    {
                        'operation_id' : gitlist_json['resultdata']['CONTENTS']['BODY'][idx_git][column_indexes_gitlist['operation_id']],
                        'git_url' : row_req['git_repositry']['url'],
                        'git_user' : payload['cd_config']['environments_common']['git_repositry']['user'],
                        'git_password' : payload['cd_config']['environments_common']['git_repositry']['token'],
                    }
                )

        globals.logger.debug('---- Git Environments Post ----')
        #logger.debug(json.dumps(gitlist_edit).encode().decode('unicode-escape'))
        # logger.debug(json.dumps(gitlist_edit))

        gitlist_edit_resp = requests.post(ita_restapi_endpoint + '?no=' + ita_menu_gitenv_param, headers=edit_headers, data=json.dumps(gitlist_edit))

        globals.logger.debug('---- Git Environments Post Response ----')
        #logger.debug(gitlist_edit_resp.text.encode().decode('unicode-escape'))
        # globals.logger.debug(gitlist_edit_resp.text)

        # 正常終了
        ret_status = 200

        # 戻り値をそのまま返却        
        return jsonify({"result": ret_status, "rows": response["items"]}), ret_status

    except common.UserException as e:
        return common.server_error_to_message(e, app_name + exec_stat, error_detail)
    except Exception as e:
        return common.server_error_to_message(e, app_name + exec_stat, error_detail)


def column_indexes(column_names, row_header):
    """項目位置の取得 Get item position

    Args:
        column_names (str[]): column names 
        row_header (str): row header

    Returns:
        int: column index
    """
    column_indexes = {}
    for idx in column_names:
        column_indexes[idx] = row_header.index(column_names[idx])
    return column_indexes

def search_opration(opelist, column_indexes, git_url):
    """オペレーションの検索 search operation

    Args:
        opelist (dict): operation info. 
        column_indexes (dict): column indexes
        git_url (str): git url

    Returns:
        int: -1:error , other: index 
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
            return idx

    # 存在しないとき
    return -1

#
# オペレーション選択文字列の生成
#
def format_opration_info(operow, column_indexes):
    return operow[column_indexes['operation_date']] + '_' + operow[column_indexes['operation_id']] + ':' + operow[column_indexes['operation_name']]

#
# git情報の検索
#
def search_gitlist(gitlist, column_indexes, git_url):
    for idx, row in enumerate(gitlist):
        if idx == 0:
            # 1行目はヘッダなので読み飛ばし
            continue

        if row[column_indexes_common["delete"]] != "":
            # 削除は無視
            continue

        if git_url == row[column_indexes['git_url']]:
            # git_urlが存在したとき
            return idx

    # 存在しないとき
    return -1


def settings_manifest_parameter(workspace_id):
    """manifest parameter setting

    Returns:
        Response: HTTP Respose
    """

    app_name = "ワークスペース情報:"
    exec_stat = "実行環境取得"
    error_detail = ""

    try:
        globals.logger.debug('#' * 50)
        globals.logger.debug('CALL {}'.format(inspect.currentframe().f_code.co_name))
        globals.logger.debug('#' * 50)

        # パラメータ情報(JSON形式) prameter save
        payload = request.json.copy()

        # ワークスペースアクセス情報取得
        access_info = api_access_info.get_access_info(workspace_id)

        # namespaceの取得
        namespace = common.get_namespace_name(workspace_id)

        ita_restapi_endpoint = "http://{}.{}.svc:{}/default/menu/07_rest_api_ver1.php".format(EPOCH_ITA_HOST, namespace, EPOCH_ITA_PORT)
        ita_user = access_info['ITA_USER']
        ita_pass = access_info['ITA_PASSWORD']

        # HTTPヘッダの生成
        filter_headers = {
            'host': EPOCH_ITA_HOST + ':' + EPOCH_ITA_PORT,
            'Content-Type': 'application/json',
            'Authorization': base64.b64encode((ita_user + ':' + ita_pass).encode()),
            'X-Command': 'FILTER',
        }

        edit_headers = {
            'host': EPOCH_ITA_HOST + ':' + EPOCH_ITA_PORT,
            'Content-Type': 'application/json',
            'Authorization': base64.b64encode((ita_user + ':' + ita_pass).encode()),
            'X-Command': 'EDIT',
        }

        # globals.logger.debug(payload)

        #
        # オペレーションの取得
        #
        opelist_resp = requests.post(ita_restapi_endpoint + '?no=' + ite_menu_operation, headers=filter_headers)
        opelist_json = json.loads(opelist_resp.text)
        globals.logger.debug('---- Operation ----')
        # logger.debug(opelist_resp.text)
        # logger.debug(opelist_json)

        # 項目位置の取得
        column_indexes_opelist = column_indexes(column_names_opelist, opelist_json['resultdata']['CONTENTS']['BODY'][0])
        globals.logger.debug('---- Operation Index ----')
        # logger.debug(column_indexes_opelist)

        #
        # マニフェスト環境パラメータの取得
        #
        content = {
            "1": {
                "NORMAL": "0"
            }
        }
        maniparam_resp = requests.post(ita_restapi_endpoint + '?no=' + ita_menu_manifest_param, headers=filter_headers, data=json.dumps(content))
        maniparam_json = json.loads(maniparam_resp.text)
        globals.logger.debug('---- Current Manifest Parameters ----')
        # logger.debug(maniparam_resp.text)
        globals.logger.debug(maniparam_json)

        # 項目位置の取得
        column_indexes_maniparam = column_indexes(column_names_manifest_param, maniparam_json['resultdata']['CONTENTS']['BODY'][0])
        globals.logger.debug('---- Manifest Parameters Index ----')
        # logger.debug(column_indexes_maniparam)

        # Responseデータの初期化
        response = {"result":"200",}

        globals.logger.debug("opelist:{}".format(opelist_json['resultdata']['CONTENTS']['BODY']))
        # マニフェスト環境パラメータのデータ成型
        maniparam_edit = []
        for environment in payload['ci_config']['environments']:
            
            idx_ope = -1
            # cd_configの同一環境情報からgit_urlを取得する Get git_url from the same environment information in cd_config
            for cd_environment in payload['cd_config']['environments']:
                if environment['environment_id'] == cd_environment['environment_id']:
                    globals.logger.debug("git_url:{}".format(cd_environment['git_repositry']['url']))
                    idx_ope = search_opration(opelist_json['resultdata']['CONTENTS']['BODY'], column_indexes_opelist, cd_environment['git_repositry']['url'])

            # ITAからオペレーション(=環境)が取得できなければ異常
            if idx_ope == -1:
                error_detail = "CD環境が設定されていません。"
                raise common.UserException(error_detail)

            req_maniparam_operation_id = opelist_json['resultdata']['CONTENTS']['BODY'][idx_ope][column_indexes_common['record_no']]

            for idx_manifile, row_manifile in enumerate(environment['manifests']):

                image = None
                image_tag = None
                param01 = None
                param02 = None
                param03 = None
                param04 = None
                param05 = None
                param06 = None
                param07 = None
                param08 = None
                param09 = None
                param10 = None
                param11 = None
                param12 = None
                param13 = None
                param14 = None
                param15 = None
                param16 = None
                param17 = None
                param18 = None
                param19 = None
                param20 = None
                # parameters成型
                for key, value in row_manifile['parameters'].items():
                    if key == 'image':
                        image = value
                    elif key == 'image_tag':
                        image_tag = value
                    elif key == 'param01':
                        param01 = value
                    elif key == 'param02':
                        param02 = value
                    elif key == 'param03':
                        param03 = value
                    elif key == 'param04':
                        param04 = value
                    elif key == 'param05':
                        param05 = value
                    elif key == 'param06':
                        param06 = value
                    elif key == 'param07':
                        param07 = value
                    elif key == 'param08':
                        param08 = value
                    elif key == 'param09':
                        param09 = value
                    elif key == 'param10':
                        param10 = value
                    elif key == 'param11':
                        param11 = value
                    elif key == 'param12':
                        param12 = value
                    elif key == 'param13':
                        param13 = value
                    elif key == 'param14':
                        param14 = value
                    elif key == 'param15':
                        param15 = value
                    elif key == 'param16':
                        param16 = value
                    elif key == 'param17':
                        param17 = value
                    elif key == 'param18':
                        param18 = value
                    elif key == 'param19':
                        param19 = value
                    elif key == 'param20':
                        param20 = value

                # 既存データ確認
                maniparam_id = -1
                for idx_maniparam, row_maniparam in enumerate(maniparam_json['resultdata']['CONTENTS']['BODY']):
                    current_maniparam_operation_id = row_maniparam[column_indexes_maniparam['operation_id']]
                    current_maniparam_include_index = row_maniparam[column_indexes_maniparam['indexes']]
                    if current_maniparam_operation_id == req_maniparam_operation_id and \
                            current_maniparam_include_index == str(idx_manifile + 1):
                        maniparam_id = row_maniparam[column_indexes_common['record_no']]
                        break

                if maniparam_id == -1:
                    # 追加処理データの設定
                    maniparam_edit.append(
                        {
                            str(column_indexes_common['method']) : param_value_method_entry,
                            str(column_indexes_maniparam['host']) : param_value_host,
                            str(column_indexes_maniparam['operation']) : format_opration_info(opelist_json['resultdata']['CONTENTS']['BODY'][idx_ope], column_indexes_opelist),
                            str(column_indexes_maniparam['indexes']) : idx_manifile + 1,
                            str(column_indexes_maniparam['image']) : image,
                            str(column_indexes_maniparam['image_tag']) : image_tag,
                            str(column_indexes_maniparam['param01']) : param01,
                            str(column_indexes_maniparam['param02']) : param02,
                            str(column_indexes_maniparam['param03']) : param03,
                            str(column_indexes_maniparam['param04']) : param04,
                            str(column_indexes_maniparam['param05']) : param05,
                            str(column_indexes_maniparam['param06']) : param06,
                            str(column_indexes_maniparam['param07']) : param07,
                            str(column_indexes_maniparam['param08']) : param08,
                            str(column_indexes_maniparam['param09']) : param09,
                            str(column_indexes_maniparam['param10']) : param10,
                            str(column_indexes_maniparam['param11']) : param11,
                            str(column_indexes_maniparam['param12']) : param12,
                            str(column_indexes_maniparam['param13']) : param13,
                            str(column_indexes_maniparam['param14']) : param14,
                            str(column_indexes_maniparam['param15']) : param15,
                            str(column_indexes_maniparam['param16']) : param16,
                            str(column_indexes_maniparam['param17']) : param17,
                            str(column_indexes_maniparam['param18']) : param18,
                            str(column_indexes_maniparam['param19']) : param19,
                            str(column_indexes_maniparam['param20']) : param20,
                            str(column_indexes_maniparam['template_name']) : '"{{ TPF_epoch_template_yaml' + str(idx_manifile + 1) + ' }}"',
                        }
                    )
                    globals.logger.debug('---- Manifest Parameters Item(Add) ----')
                    globals.logger.debug(maniparam_edit[len(maniparam_edit) -1])

                else:
                    # 更新処理
                    maniparam_edit.append(
                        {
                            str(column_indexes_common['method']) : param_value_method_update,
                            str(column_indexes_common['record_no']) : maniparam_id,
                            str(column_indexes_maniparam['host']) : maniparam_json['resultdata']['CONTENTS']['BODY'][idx_maniparam][column_indexes_maniparam['host']],
                            str(column_indexes_maniparam['operation']) : maniparam_json['resultdata']['CONTENTS']['BODY'][idx_maniparam][column_indexes_maniparam['operation']],
                            str(column_indexes_maniparam['indexes']) : maniparam_json['resultdata']['CONTENTS']['BODY'][idx_maniparam][column_indexes_maniparam['indexes']],
                            str(column_indexes_maniparam['image']) : image,
                            str(column_indexes_maniparam['image_tag']) : image_tag,
                            str(column_indexes_maniparam['param01']) : param01,
                            str(column_indexes_maniparam['param02']) : param02,
                            str(column_indexes_maniparam['param03']) : param03,
                            str(column_indexes_maniparam['param04']) : param04,
                            str(column_indexes_maniparam['param05']) : param05,
                            str(column_indexes_maniparam['param06']) : param06,
                            str(column_indexes_maniparam['param07']) : param07,
                            str(column_indexes_maniparam['param08']) : param08,
                            str(column_indexes_maniparam['param09']) : param09,
                            str(column_indexes_maniparam['param10']) : param10,
                            str(column_indexes_maniparam['param11']) : param11,
                            str(column_indexes_maniparam['param12']) : param12,
                            str(column_indexes_maniparam['param13']) : param13,
                            str(column_indexes_maniparam['param14']) : param14,
                            str(column_indexes_maniparam['param15']) : param15,
                            str(column_indexes_maniparam['param16']) : param16,
                            str(column_indexes_maniparam['param17']) : param17,
                            str(column_indexes_maniparam['param18']) : param18,
                            str(column_indexes_maniparam['param19']) : param19,
                            str(column_indexes_maniparam['param20']) : param20,
                            str(column_indexes_maniparam['template_name']) : maniparam_json['resultdata']['CONTENTS']['BODY'][idx_maniparam][column_indexes_maniparam['template_name']],
                            str(column_indexes_maniparam['lastupdate']) : maniparam_json['resultdata']['CONTENTS']['BODY'][idx_maniparam][column_indexes_maniparam['lastupdate']],
                        }
                    )
                    globals.logger.debug('---- Manifest Parameters Item(Update) ----')
                    globals.logger.debug(maniparam_edit[len(maniparam_edit) -1])

        globals.logger.debug('---- Deleting Manifest Parameters Setting ----')
        # 既存データをすべて廃止する
        for idx_maniparam, row_maniparam in enumerate(maniparam_json['resultdata']['CONTENTS']['BODY']):
            # 1行目無視する
            if idx_maniparam == 0:
                continue
            flgExists = False
            for idx_edit, row_edit in enumerate(maniparam_edit):
                # 該当するrecord_noがあれば、チェックする
                if str(column_indexes_common['record_no']) in row_edit:
                    if row_edit[str(column_indexes_common['record_no'])] == row_maniparam[column_indexes_common['record_no']]:
                        flgExists = True
                        break
            
            # 該当するレコードがない場合は、廃止として追加する
            if not flgExists:
                # 削除用のデータ設定
                maniparam_edit.append(
                    {
                        str(column_indexes_common['method']) : param_value_method_delete,
                        str(column_indexes_common['record_no']) : row_maniparam[column_indexes_common['record_no']],
                        str(column_indexes_maniparam['lastupdate']) : row_maniparam[column_indexes_maniparam['lastupdate']],
                    }
                )

        globals.logger.debug('---- Updating Manifest Parameters ----')
        # globals.logger.debug(json.dumps(maniparam_edit))

        manuparam_edit_resp = requests.post(ita_restapi_endpoint + '?no=' + ita_menu_manifest_param, headers=edit_headers, data=json.dumps(maniparam_edit))
        maniparam_json = json.loads(manuparam_edit_resp.text)

        globals.logger.debug('---- Manifest Parameters Post Response ----')
        # logger.debug(manuparam_edit_resp.text)
        # globals.logger.debug(maniparam_json)

        if maniparam_json["status"] != "SUCCEED" or maniparam_json["resultdata"]["LIST"]["NORMAL"]["error"]["ct"] != 0:
            raise common.UserException(manuparam_edit_resp.text.encode().decode('unicode-escape'))

        # 正常終了
        ret_status = 200

        # 戻り値をそのまま返却        
        return jsonify({"result": ret_status}), ret_status

    except common.UserException as e:
        return common.server_error_to_message(e, app_name + exec_stat, error_detail)
    except Exception as e:
        return common.server_error_to_message(e, app_name + exec_stat, error_detail)


# GitUrlの検索
#
def search_git_url(opelist, column_indexes, operation_id):
    for idx, row in enumerate(opelist):
        if idx == 0:
            # 1行目はヘッダなので読み飛ばし
            continue

        if row[column_indexes_common["delete"]] != "":
            # 削除は無視
            continue

        # logger.debug('operation_id:')
        # logger.debug(operation_id)
        # logger.debug('row[column_indexes[remarks]]:')
        # logger.debug(row[column_indexes['remarks']])
        if operation_id == row[column_indexes['operation_id']]:
            # 備考にgit_urlが含まれているとき
            globals.logger.debug('find:' + str(idx))
            return row[column_indexes['remarks']]

    # 存在しないとき
    return -1

#
# オペレーション選択文字列の生成
#
def format_opration_info(operow, column_indexes):
    return operow[column_indexes['operation_date']] + '_' + operow[column_indexes['operation_id']] + ':' + operow[column_indexes['operation_name']]

#
# git情報の検索
#
def search_maniparam(maniparam, column_indexes, git_url):
    for idx, row in enumerate(maniparam):
        if idx == 0:
            # 1行目はヘッダなので読み飛ばし
            continue

        if row[column_indexes_common["delete"]] != "":
            # 削除は無視
            continue

        if git_url == row[column_indexes['git_url']]:
            # git_urlが存在したとき
            return idx

    # 存在しないとき
    return -1

def settings_manifest_templates(workspace_id):
    """manifest templates setting

    Returns:
        Response: HTTP Respose
    """

    app_name = "ワークスペース情報:"
    exec_stat = "manifestテンプレートファイル登録"
    error_detail = ""

    try:
        globals.logger.debug('#' * 50)
        globals.logger.debug('CALL {}'.format(inspect.currentframe().f_code.co_name))
        globals.logger.debug('#' * 50)

        # パラメータ情報(JSON形式) prameter save
        payload = request.json.copy()

        # ワークスペースアクセス情報取得
        access_info = api_access_info.get_access_info(workspace_id)

        # namespaceの取得
        namespace = common.get_namespace_name(workspace_id)

        ita_restapi_endpoint = "http://{}.{}.svc:{}/default/menu/07_rest_api_ver1.php".format(EPOCH_ITA_HOST, namespace, EPOCH_ITA_PORT)
        ita_user = access_info['ITA_USER']
        ita_pass = access_info['ITA_PASSWORD']

        # HTTPヘッダの生成
        filter_headers = {
            'host': EPOCH_ITA_HOST + ':' + EPOCH_ITA_PORT,
            'Content-Type': 'application/json',
            'Authorization': base64.b64encode((ita_user + ':' + ita_pass).encode()),
            'X-Command': 'FILTER',
        }

        edit_headers = {
            'host': EPOCH_ITA_HOST + ':' + EPOCH_ITA_PORT,
            'Content-Type': 'application/json',
            'Authorization': base64.b64encode((ita_user + ':' + ita_pass).encode()),
            'X-Command': 'EDIT',
        }

        #
        # マニフェストテンプレートの取得
        #
        content = {
            "1": {
                "NORMAL": "0"
            },
            "3": {
                "NORMAL": "TPF_epoch_template_yaml"
            },
        }
        manitpl_resp = requests.post(ita_restapi_endpoint + '?no=' + ita_menu_manifest_template, headers=filter_headers, data=json.dumps(content))
        manitpl_json = json.loads(manitpl_resp.text)
        globals.logger.debug('---- Current Manifest Templates ----')
        # logger.debug(manitpl_resp.text)
        # globals.logger.debug(manitpl_json)

        req_data = payload['manifests']
        mani_req_len = len(req_data)
        mani_ita_len = manitpl_json['resultdata']['CONTENTS']['RECORD_LENGTH']
        max_loop_cnt = max(mani_req_len, mani_ita_len)
        globals.logger.debug("max_loop_cnt: " + str(max_loop_cnt))

        ita_data = manitpl_json['resultdata']['CONTENTS']["BODY"]
        ita_data.pop(0)
        # globals.logger.debug(ita_data)

        edit_data = {
            "UPLOAD_FILE": []
        }
        tpl_cnt = 0
        for i in range(max_loop_cnt):

            # ITAを廃止
            if i > mani_req_len - 1:
                tmp_data = []
                for j, item in enumerate(ita_data[i]):
                    if j == 0:
                        tmp_data.append('廃止')
                    else:
                        tmp_data.append(item)

                edit_data[str(i)] = tmp_data

            # ITAに新規登録する
            elif i > mani_ita_len - 1:
                tpl_cnt += 1
                tmp_data = {}
                tmp_data['0'] = "登録"
                tmp_data['3'] = "TPF_epoch_template_yaml" + str(tpl_cnt)
                tmp_data['4'] = req_data[i]["file_name"]
                tmp_data['5'] = "VAR_image:\n"\
                                "VAR_image_tag:\n"\
                                "VAR_param01:\n"\
                                "VAR_param02:\n"\
                                "VAR_param03:\n"\
                                "VAR_param04:\n"\
                                "VAR_param05:\n"\
                                "VAR_param06:\n"\
                                "VAR_param07:\n"\
                                "VAR_param08:\n"\
                                "VAR_param09:\n"\
                                "VAR_param10:\n"\
                                "VAR_param11:\n"\
                                "VAR_param12:\n"\
                                "VAR_param13:\n"\
                                "VAR_param14:\n"\
                                "VAR_param15:\n"\
                                "VAR_param16:\n"\
                                "VAR_param17:\n"\
                                "VAR_param18:\n"\
                                "VAR_param19:\n"\
                                "VAR_param20:"

                # Deploy方式でBlueGreenが選択された場合は、テンプレートをBlueGreen形式に自動変換する
                # When BlueGreen is selected by Deploy method, the template is automatically converted to BlueGreen format.
                if payload["deploy_method"] == "BlueGreen":
                    out_text = conv_yaml(req_data[i]["file_text"], payload["deploy_params"])
                    globals.logger.debug(out_text)
                else:
                    out_text = req_data[i]["file_text"]
                # globals.logger.debug(out_text)

                edit_data[str(i)] = tmp_data
                edit_data["UPLOAD_FILE"].append({"4": base64.b64encode(req_data[i]["file_text"].encode()).decode()})

            # ITAを更新する
            else:
                tpl_cnt += 1
                tmp_data = ita_data[i]
                tmp_data[0] = "更新"
                tmp_data[3] = "TPF_epoch_template_yaml" + str(tpl_cnt)
                tmp_data[4] = req_data[i]["file_name"]
                tmp_data[5] = "VAR_image:\n"\
                            "VAR_image_tag:\n"\
                            "VAR_param01:\n"\
                            "VAR_param02:\n"\
                            "VAR_param03:\n"\
                            "VAR_param04:\n"\
                            "VAR_param05:\n"\
                            "VAR_param06:\n"\
                            "VAR_param07:\n"\
                            "VAR_param08:\n"\
                            "VAR_param09:\n"\
                            "VAR_param10:\n"\
                            "VAR_param11:\n"\
                            "VAR_param12:\n"\
                            "VAR_param13:\n"\
                            "VAR_param14:\n"\
                            "VAR_param15:\n"\
                            "VAR_param16:\n"\
                            "VAR_param17:\n"\
                            "VAR_param18:\n"\
                            "VAR_param19:\n"\
                            "VAR_param20:"

                # Deploy方式でBlueGreenが選択された場合は、テンプレートをBlueGreen形式に自動変換する
                # When BlueGreen is selected by Deploy method, the template is automatically converted to BlueGreen format.
                if payload["deploy_method"] == "BlueGreen":
                    out_text = conv_yaml(req_data[i]["file_text"], payload["deploy_params"])
                    globals.logger.debug(out_text)
                else:
                    out_text = req_data[i]["file_text"]
                # globals.logger.debug(out_text)

                edit_data[str(i)] = tmp_data
                edit_data["UPLOAD_FILE"].append({"4": base64.b64encode(out_text.encode()).decode()})

        # globals.logger.debug(edit_data)

        # ITAへREST実行
        manutemplate_edit_resp = requests.post(ita_restapi_endpoint + '?no=' + ita_menu_manifest_template, headers=edit_headers, data=json.dumps(edit_data))
        # manitemplate_json = json.loads(manutemplate_edit_resp.text)

        # globals.logger.debug(manitemplate_json)

        # 正常終了
        ret_status = 200

        # 戻り値をそのまま返却        
        return jsonify({"result": ret_status}), ret_status

    except common.UserException as e:
        return common.server_error_to_message(e, app_name + exec_stat, error_detail)
    except Exception as e:
        return common.server_error_to_message(e, app_name + exec_stat, error_detail)

def get_keys_from_value(d, val):
    """辞書情報Value値からKey値の取得
        Obtaining the Key value from the dictionary information Value value

    Args:
        d (dict): 辞書情報 Dictionary information
        val (obj): Value値 Value

    Returns:
        obj: 該当するキー値(ない場合はNone) Applicable key value (None if none)
    """
    ret = None
    for k, v in d.items():
        if v == val:
            ret = k
            break
    return ret

def conv_yaml(file_text, params):
    """yamlファイルの解析変換 Parsing conversion of yaml file

    Args:
        file_text (str): 変換元yamlの内容 Contents of conversion source yaml
        params (dic): BlueGreen Deploy時のパラメータ(オプション値) Parameters (option value) for BlueGreen Deploy

    Returns:
        str : 変換後の内容
    """

    try:

        block_data = []
        block_keys = {}
        block_values = {}
        idx = 0
        split_text = file_text.split("\n")
        # ファイルの読み込み Read file
        for line in split_text:
            # globals.logger.debug("line:{}".format(line))
            # ":"を区切りとして要素と値に分ける
            # Divide into elements and values ​​with ":" as a delimiter
            split_line = line.split(":")
            # 区切り文字ありの場合は、Keyと値に分けて格納する
            # If there is a delimiter, store it separately as Key and value.
            if len(split_line) < 2:
                # globals.logger.debug(f"split_line:{split_line}")
                # "---"を一区切りとしてブロックの情報とする
                # Use "---" as a block information
                if line.strip() == "---":
                    block_data.append({"block": {"block_keys": block_keys,"block_values": block_values}})
                    block_data.append({"separation": line})
                    block_keys = {}
                    block_values = {}
                    idx = 0
                else:
                    # それ以外はそのまま格納
                    # Use "---" as a block information
                    block_data.append({"other": line})
            else:
                block_keys[idx] = split_line[0].rstrip() 
                block_values[idx] = split_line[1] 
                # globals.logger.debug(f"add block:{split_line}")
                idx += 1
            
        if len(block_keys) > 0:
            block_data.append({"block": {"block_keys": block_keys,"block_values": block_values}})

        out_yaml = ""
        # globals.logger.debug(f"block_data:{block_data}")
        # 加工した情報をブロック単位で処理する
        # Process processed information in block units
        for idx, values in enumerate(block_data):
            for key in values.keys():
                if key == "other" or key == "separation":
                    # globals.logger.debug(f"line:{values[key]}")
                    out_yaml += "{}\n".format(values[key])
                else:
                    # 置き換え対象のkindを検索する
                    # Search for the kind to be replaced
                    f_Deployment = False
                    f_Service = False
                    service_idx = -1
                    service_name = ""

                    if "kind" in values[key]["block_keys"].values() and \
                        "apiVersion" in values[key]["block_keys"].values() and \
                        "metadata" in values[key]["block_keys"].values():

                        kind_idx = get_keys_from_value(values[key]["block_keys"], "kind")
                        api_ver_idx = get_keys_from_value(values[key]["block_keys"], "apiVersion")
                        metadata_idx = get_keys_from_value(values[key]["block_keys"], "metadata")

                        # globals.logger.debug(f"kind_idx:{kind_idx}")
                        # globals.logger.debug(f"api_ver_idx:{api_ver_idx}")
                        # globals.logger.debug(f"metadata_idx:{metadata_idx}")

                        # globals.logger.debug("Kind:{}".format(values[key]["block_values"][kind_idx].strip()))
                        # globals.logger.debug("apiVersion:{}".format(values[key]["block_values"][api_ver_idx].strip()))



                        if values[key]["block_values"][kind_idx].strip() == "Deployment" and \
                            values[key]["block_values"][api_ver_idx].strip() == "apps/v1":
                            # f_Deployment = True
                            # pglobals.logger.debugrint("Hit!:kind:{} , apiVersion:{}".format(values[key]["block_values"][kind_idx], values[key]["block_values"][api_ver_idx]))

                            deployment_name_key = values[key]["block_keys"][metadata_idx + 1].strip()
                            deployment_name = values[key]["block_values"][metadata_idx + 1].strip()
                            service_name = deployment_name
                            # globals.logger.debug(f"deployment_name:{deployment_name}")

                            # f_Service = False
                            # service_idx = -1
                            # service_name = ""
                            ports_name = ""
                            ports_port = ""
                            ports_protocol = ""

                            # portsセクションを見つけて、その配下にあるname, containerPort, protocolの要素を抽出する
                            # Find the ports section and extract the name, containerPort, protocol elements under it
                            for keys_index, keys_values in values[key]["block_keys"].items():
                                if keys_values.strip() == "ports":
                                    # globals.logger.debug("ports found!!")
                                    # インデントの数をチェック
                                    # Check the number of indent
                                    leftspace = keys_values.rstrip().replace("ports", "")
                                    idx = keys_index + 1
                                    left_len = len(leftspace)
                                    while idx < len(values[key]["block_keys"]):
                                        # 子の項目判断
                                        # Child item judgment
                                        if values[key]["block_keys"][idx][left_len:left_len + 1] == "-" or \
                                            values[key]["block_keys"][idx][left_len:left_len + 1] == " ":
                                            if values[key]["block_keys"][idx][left_len + 2:].strip() == "name":
                                                ports_name = values[key]["block_values"][idx].strip()
                                            elif values[key]["block_keys"][idx][left_len + 2:].strip() == "containerPort":
                                                f_Deployment = True
                                                ports_port = values[key]["block_values"][idx].strip()
                                            elif values[key]["block_keys"][idx][left_len + 2:].strip() == "protocol":
                                                ports_protocol = values[key]["block_values"][idx].strip()
                                        else:
                                            break
                                        idx += 1
                                    # globals.logger.debug(f"ports_name:{ports_name}")
                                    # globals.logger.debug(f"ports_port:{ports_port}")
                                    # globals.logger.debug(f"ports_protocol:{ports_protocol}")



                            # # selector の appがDeployment nameと同じ内容を検索し、active面のサービスとして保存する
                            # # The selector app searches for the same content as the Deployment name and saves it as a service on the active side.
                            # for idx_svc, values_svc in enumerate(block_data):
                            #     for key_svc in values_svc.keys():
                            #         if key_svc != "other" and key_svc != "separation":
                            #             kind_idx = get_keys_from_value(values_svc[key_svc]["block_keys"], "kind")
                            #             api_ver_idx = get_keys_from_value(values_svc[key_svc]["block_keys"], "apiVersion")
                            #             metadata_idx = get_keys_from_value(values_svc[key_svc]["block_keys"], "metadata")
                            #             selector_idx = get_keys_from_value(values_svc[key_svc]["block_keys"], "  selector")
                            #             # globals.logger.debug(f"kind_idx:{kind_idx}")
                            #             # globals.logger.debug(f"api_ver_idx:{api_ver_idx}")
                            #             # globals.logger.debug(f"metadata_idx:{metadata_idx}")
                            #             # globals.logger.debug(f"selector_idx:{selector_idx}")
                            #             # globals.logger.debug(values_svc[key_svc]["block_values"][selector_idx])

                            #             if values_svc[key_svc]["block_values"][kind_idx].strip() == "Service" and \
                            #                 values_svc[key_svc]["block_values"][api_ver_idx].strip() == "v1" and \
                            #                 values_svc[key_svc]["block_values"][selector_idx + 1].strip() == deployment_name:

                            #                 service_idx = idx_svc
                            #                 service_name = values_svc[key_svc]["block_values"][metadata_idx + 1].strip() 
                            #                 f_Service = True
                            #                 break

                            #     if f_Service:
                            #         break

                    if f_Deployment:
                        # globals.logger.debug(f"service_name:{service_name}")
                        service_name_preview = service_name + "-preview"

                    # BlueGreen対応のyaml生成
                    # BlueGreen compatible yaml generation
                    for block_idx, block_key in values[key]["block_keys"].items():
                        # deploymentの場合は、BlueGreenのyamlに置き換える
                        # For deployment, replace with BlueGreen yaml
                        if f_Deployment:
                            if block_key == "kind":
                                value = " Rollout"
                            elif block_key == "apiVersion":
                                value = " argoproj.io/v1alpha1"
                            else:
                                value = values[key]["block_values"][block_idx]
                        else:
                            value = values[key]["block_values"][block_idx]

                        # globals.logger.debug(f"line:{block_key}:{value}")
                        out_yaml += f"{block_key}:{value}\n"

                    # Rolloutのオプション値設定
                    # Rollout option value setting
                    if f_Deployment:
                        out_yaml += "  {}:\n".format("strategy")
                        out_yaml += "    {}:\n".format("blueGreen")
                        out_yaml += "      {}: {}\n".format("activeService", service_name)
                        out_yaml += "      {}: {}\n".format("previewService", service_name_preview)
                        for key, value in params.items():
                            out_yaml += "      {}: {}\n".format(key, value)
                        # out_yaml += "      {}: {}\n".format("scaleDownDelaySeconds", 120)

                        # preview面のサービスを追加
                        # Added preview service

                        out_yaml += "---\n"
                        out_yaml += "{}: {}\n".format("apiVersion", "v1")
                        out_yaml += "{}: {}\n".format("kind", "Service")
                        out_yaml += "{}:\n".format("metadata")
                        out_yaml += "  {}: {}\n".format("name", service_name_preview)
                        out_yaml += "  {}:\n".format("labels")
                        out_yaml += "    {}: {}\n".format("name", service_name_preview)
                        out_yaml += "{}:\n".format("spec")
                        out_yaml += "  {}: {}\n".format("type", "ClusterIP")
                        out_yaml += "  {}\n".format("ports")
                        str_sep = "- "
                        if ports_name:
                            out_yaml += "  {}{}: {}\n".format(str_sep, "name", ports_name)
                            str_sep = "  "
                        if ports_port:
                            out_yaml += "  {}{}: {}\n".format(str_sep, "port", ports_port)
                            out_yaml += "  {}{}: {}\n".format(str_sep, "targetPort", ports_port)
                            str_sep = "  "
                        if ports_protocol:
                            out_yaml += "  {}{}: {}\n".format(str_sep, "protocol", ports_protocol)
                            str_sep = "  "
                        out_yaml += "  {}\n".format("selector")
                        out_yaml += "    {}: {}\n".format(deployment_name_key, deployment_name)

        # globals.logger.debug(f"out_yaml:{out_yaml}")

        return out_yaml
    
    except Exception as e:
        raise
