#   Copyright 2019 NEC Corporation
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

from flask import jsonify
import random, string
import json

import globals
from kubernetes import client, config

class UserException(Exception):
    pass

def delete_dict_key(dictobj, key):
    """Dictionary Key削除

    Args:
        dictobj (dict): Dictionary
        key (any): key
    """
    if key in dictobj:
        del dictobj[key]

def random_string(n):
    """ランダム文字列生成

    Args:
        n (int): 文字数

    Returns:
        str: ランダム文字列
    """
    return ''.join(random.choices(string.ascii_letters + string.digits, k=n))


def server_error(e):
    """サーバーエラーレスポンス

    Args:
        e (Exception): 例外

    Returns:
        response: HTTP Response (HTTP-500)
    """
    import traceback

    globals.logger.error(''.join(list(traceback.TracebackException.from_exception(e).format())))

    return jsonify(
        {
            'result':       '500',
            'exception':    ''.join(list(traceback.TracebackException.from_exception(e).format())),
        }
    ), 500

def server_error_to_message(e, error_statement, error_detail):
    """サーバーエラーレスポンス(メッセージ付き)

    Args:
        e (Exception): 例外
        error_statement (str): エラー情報（処理内容）
        error_detail (str): エラー情報詳細

    Returns:
        response: HTTP Response (HTTP-500)
    """
    import traceback

    globals.logger.error(''.join(list(traceback.TracebackException.from_exception(e).format())))

    return jsonify(
        {
            'result':       '500',
            'errorStatement': error_statement,
            'errorDetail':  error_detail,
            'exception':    ''.join(list(traceback.TracebackException.from_exception(e).format())),
        }
    ), 500


def is_json_format(str):
    """json値判断

    Args:
        str (str): json文字列

    Returns:
        bool: True:json, False:not json
    """
    try:
        # Exceptionで引っかかるときはすべてJson意外と判断
        json.loads(str)
    except json.JSONDecodeError:
        return False
    except ValueError:
        return False
    except Exception:
        return False
    return True


def get_namespace_name(workspace_id):
    """workspace_idに対するnamespace名取得

    Args:
        workspace_id (int): ワークスペースID

    Returns:
        str: namespace name
    """
    return  'epoch-ws-{}'.format(workspace_id)

def get_namespace(name):
    """namespace情報取得

    Args:
        name (str): namespace名

    Returns:
        namespace is exist：
            namespace info (str)
        namespace is not exist：
            None
    """
    try:
        config.load_incluster_config()
        # 使用するAPIの宣言
        v1 = client.CoreV1Api()
        
        # namespaceの情報取得
        globals.logger.debug('get namespace :')
        ret = v1.read_namespace(name=name)

        globals.logger.debug("ret: %s" % (ret))
        return ret 

    except Exception as e:
        globals.logger.debug("Except: %s" % (e))
        return None 
      
def create_namespace(name):
    """namespace作成

    Args:
        name (str): namespace名

    Returns:
        namespace created：
            namespace create info (str)
        namespace create failed：
            None
    """
    try:
        config.load_incluster_config()

        # 使用するAPIの宣言
        v1 = client.CoreV1Api()
        
        # 引数の設定
        body = client.V1Namespace(metadata=client.V1ObjectMeta(name=name))

        # namespaceの作成
        globals.logger.debug('create namespace :')
        ret = v1.create_namespace(body=body)

        globals.logger.debug("ret: %s" % (ret))
        return ret 

    except Exception as e:
        globals.logger.debug("Except: %s" % (e))
        return None
