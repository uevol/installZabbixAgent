# -*- coding: utf-8 -*-
# @Author: yangwei
# @Date:   2018-03-27 16:10:50
# @Last Modified by:   yangwei
# @Last Modified time: 2018-04-02 19:38:51

# #############################################################################################
# 脚本功能: 该脚本用户安装zabbix客户端，并自动发现oracle和websphere服务，并关联相关模板
# 使用说明: 1. 使用请必须按实际情况修改 custom info 的相关信息，信息说明如下：
#             -- zabbixServerIP： zabbix服务端的ip地址
#             -- zabbixURL：zabbix访问地址， 无需修改
#             -- zabbixUser： zabbix登录用户名
#             -- zabbixPass zabbix登录密码
#             -- zabbixAgentVersion: zabbix-agent版本
#             -- ftp: 文件服务器地址，用于存放安装包
#             -- oracleTemplate: oracle模板名称, 需提前在web中配置
#             -- webSphereTemplate: websphere模板名称, 需提前在web中配置

#          2. 须提前在actions中配置主机自动注册服务
#			  action --》Conditions --》Host metadata like auto_install
#			  Operations --》 Add host

#          3. 须提前在模板中配置oracle和websphere的模板，模板名称须与custom info中一致

# 运行方式: 1. 可以将脚本放在与安装包相同的文件服务器上，在要安装的机器运行以下命令：
#             curl -k http://192.168.3.197:8000/installZagent.py | python

#          2. 将脚本上传至要安装机器，运行以下命令：
#             python installZagent.py
# #############################################################################################


import commands
import sys
import os
import platform
import socket
import json
import urllib
import pprint
try:
    import urllib2
except ImportError:
    # Since Python 3, urllib2.Request and urlopen were moved to the urllib.request.
    import urllib.request as urllib2

version = platform.platform().split('-')[-2].split('.')[0]
arch = platform.platform().split('-')[-5]

# custom info
zabbixServerIP = '192.168.3.171'
zabbixUser = 'Admin'
zabbixPass = 'zabbix'
zabbixAgentVersion = '3.4.6-1'
ftp = 'http://192.168.3.197:8000/'
oracleTemplate = 'oracle'
webSphereTemplate = 'websphere'

# don't change
zabbixURL = 'http://' + zabbixServerIP + '/zabbix'
zabbixAgent = 'zabbix-agent-%s.el%s.%s.rpm'%(zabbixAgentVersion, version, arch)


class ZabbixAPI(object):
    """
    ZabbixAPI class, implement interface to zabbix api.

    :type url: str
    :param url: URL to zabbix api. Default: `ZABBIX_URL` or `https://localhost/zabbix`

    :type user: str
    :param user: Zabbix user name. Default: `ZABBIX_USER` or `admin`.

    :type password: str
    :param password: Zabbix user password. Default `ZABBIX_PASSWORD` or `zabbix`.

    """
    def __init__(self, url=None, user=None, password=None ):

        url = url or os.environ.get('ZABBIX_URL') or 'https://localhost/zabbix'
        user = user or os.environ.get('ZABBIX_USER') or 'Admin'
        password = password or os.environ.get('ZABBIX_PASSWORD') or 'zabbix'

        self.auth = None
        self.url = url + '/api_jsonrpc.php'
        self._login(user, password)

    def _login(self, user, password):
        """Do login to zabbix server.
        :type user: str
        :param user: Zabbix user
        :type password: str
        :param password: Zabbix user password
        """
        res_json = self.do_request('user.login', params={"user": user, "password": password})
        if 'error' in res_json:
            print '==================== login failed =================='
            print "Auth Failed, Please Check Your Name And Password"
            print '===================================================='
        else:
            self.auth = res_json


    def do_request(self, method, params=None):
        """Make request to Zabbix API.
        :type method: str
        :param method: ZabbixAPI method, like: `apiinfo.version`.
        :type params: str
        :param params: ZabbixAPI method arguments.
        >>> from pyzabbix import ZabbixAPI
        >>> z = ZabbixAPI()
        >>> apiinfo = z.do_request('apiinfo.version')
        """

        request_json = {
            'jsonrpc': '2.0',
            'method': method,
            'params': params or {},
            'id': '1',
        }

        # apiinfo.version and user.login doesn't require auth token
        if self.auth and (method not in ('apiinfo.version', 'user.login')):
            request_json['auth'] = self.auth

        data = json.dumps(request_json)
        if not isinstance(data, bytes):
            data = data.encode("utf-8")

        req = urllib2.Request(self.url, data)
        req.add_header('Content-Type', 'application/json-rpc')

        try:
            res = urllib2.urlopen(req)
            res_str = res.read().decode('utf-8')
            res_json = json.loads(res_str)
            if 'error' in res_json:
                print '=================================== error ========================='
                print res_json.get('error')['data']
                print '==================================================================='
            result = res_json.get('result', '')
        except Exception as e:
          raise e

        return result

    def get_template_by_name(self, template_name):
        params = {"output": "extend", "filter": {"host": [template_name]}}
        template = self.do_request("template.get", params)
        templateid = ''
        if template:
            templateid = template[0]['templateid']
        return templateid

    def get_hostid_by_ip(self, ip):
        params = {"output": ['hostid'], "filter": {"ip": ip}}
        host = self.do_request("hostinterface.get", params)
        hostid = ''
        if host:
            hostid = host[0]['hostid']
        return hostid

    def massadd_template(self, templateid, hostid):
        params = {'templates': [{'templateid': templateid}], 'hosts': [{'hostid': hostid}]}
        ret = self.do_request("template.massadd", params)
        templateid = ''
        if ret:
            templateid = ret['templateids'][0]
        return templateid

def getOracle():
    output = commands.getoutput('ps -ef | grep -i ora_smon_ | grep -v grep')
    return output

def getWebSphere():
    output = commands.getoutput('ps -ef | grep -i was | grep -v grep')
    return output

def getIp():
    try:
        s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        s.connect((zabbixServerIP, 80))
        ip = s.getsockname()[0]
    except Exception as e:
        raise e
    finally:
        s.close()
    return ip
 
def removeZabbixAgent():
    try:
        process = commands.getoutput('ps -ef | grep zabbix_agentd | grep -v grep')
        rpm = commands.getoutput('rpm -qa | grep zabbix-agent')
        file = os.path.exists('/etc/zabbix')
        if process:
            os.system('service zabbix-agent stop')
        if rpm:
            os.system('rpm -e zabbix-agent')
        if file:
            os.system('rm -rf /etc/zabbix')
    except Exception as e:
        raise e

def InstallZabbixAgent():
    try:
        is_installed = False
        removeZabbixAgent()
        source = ftp + zabbixAgent
        print('****************** start to install zabbix-agent ******************')
        out = os.system('rpm -ivh %s'%(source))
        rpm = commands.getoutput('rpm -qa | grep zabbix-agent')
        if rpm:
            os.system("sed -i 's/^Server=.*/Server=%s/g' /etc/zabbix/zabbix_agentd.conf"%(zabbixServerIP))
            os.system("sed -i 's/^ServerActive=.*/ServerActive=%s/g' /etc/zabbix/zabbix_agentd.conf"%(zabbixServerIP))
            os.system("sed -i s/^Hostname=.*/Hostname=%s/g /etc/zabbix/zabbix_agentd.conf"%(getIp()))
            # hostMetadata = ' '.join(filter(lambda x:x, ['auto_install', findOracle(), findWebSphere()]))
            os.system("echo 'HostMetadata=auto_install' >> /etc/zabbix/zabbix_agentd.conf")
            status = commands.getoutput("chkconfig zabbix-agent on && service zabbix-agent start")
            process = commands.getoutput('ps -ef | grep zabbix_agentd | grep -v grep')
            if process:
                is_installed = True
                print('****************** install successfully ******************')
            else:
                print('****************** fail to install agent *******************')
                print(status)
        else:
            print('****************** fail to install agent *******************')
    except Exception as e:
        raise e
    finally:
        return is_installed

def Link_template_to_host(template_name, ip):
    try:
        zapi = ZabbixAPI(zabbixURL, zabbixUser, zabbixPass)
        templateid = zapi.get_template_by_name(template_name)
        hostid = zapi.get_hostid_by_ip(ip)
        if templateid and hostid:
            tid = zapi.massadd_template(templateid, hostid)
            if tid:
                print('Link template %s to %s'%(template_name, ip))
        elif templateid:
            print('Can not find the host in zabbix')
        else:
            print('Can not find the template in zabbix')
    except Exception as e:
        raise e


if __name__ == "__main__":
    try:
        ret = InstallZabbixAgent()
        if ret:
            if getOracle():
                print('************* start to link %s **************'%(oracleTemplate))
                Link_template_to_host(oracleTemplate, getIp())
            if getWebSphere():
                print('************* start to link %s **************'%(webSphereTemplate))
                Link_template_to_host(webSphereTemplate, getIp())
    except Exception as e:
        raise e