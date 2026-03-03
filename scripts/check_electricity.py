import os
import sys
import json
import re
import time
from urllib.parse import urlencode, quote
from datetime import datetime, timezone, timedelta
import requests

# ---------- 工具函数 ----------
def format_utc8(dt=None):
    """返回北京时间 (UTC+8) 的字符串"""
    if dt is None:
        dt = datetime.now(timezone(timedelta(hours=8)))
    else:
        dt = dt.astimezone(timezone(timedelta(hours=8)))
    return dt.strftime("%Y-%m-%d %H:%M:%S UTC+8")

def parse_number(value):
    """将可能的字符串/数字转换为浮点数，失败返回 None"""
    if isinstance(value, (int, float)):
        return float(value)
    if isinstance(value, str):
        # 移除非数字字符（保留小数点）
        cleaned = re.sub(r'[^\d.-]', '', value)
        try:
            return float(cleaned)
        except ValueError:
            return None
    return None

def get_by_path(obj, path):
    """通过点分隔路径取值，如 'data.0.value'"""
    parts = path.split('.')
    current = obj
    for part in parts:
        if current is None:
            return None
        if part.isdigit():
            try:
                current = current[int(part)]
            except (IndexError, TypeError):
                return None
        else:
            if isinstance(current, dict):
                current = current.get(part)
            else:
                return None
    return current

def extract_balance(payload, balance_path=None):
    """从响应中提取余额，模拟 Worker 中的 extractBalance"""
    if balance_path:
        val = get_by_path(payload, balance_path)
        num = parse_number(val)
        if num is not None:
            return num

    # 递归查找包含关键字的数值
    def search(node):
        if isinstance(node, dict):
            # 先检查是否有 name/value 对
            name = node.get('name') or node.get('label') or node.get('title')
            value = node.get('value') or node.get('val') or node.get('amount') or node.get('num')
            if name and value is not None:
                lowered = name.lower()
                if any(k in lowered for k in ['剩余', '余额', '电量', 'remain', 'balance', 'electricity']):
                    num = parse_number(value)
                    if num is not None:
                        return num
            # 递归遍历所有值
            for v in node.values():
                res = search(v)
                if res is not None:
                    return res
        elif isinstance(node, list):
            for item in node:
                res = search(item)
                if res is not None:
                    return res
        elif isinstance(node, str):
            # 从文本中提取
            patterns = [
                r'(?:剩余购电量|剩余电量|当前电量|余额|剩余)\s*[:：]?\s*(-?\d+(?:\.\d+)?)',
                r'(-?\d+(?:\.\d+)?)\s*度'
            ]
            for p in patterns:
                m = re.search(p, node)
                if m:
                    num = parse_number(m.group(1))
                    if num is not None:
                        return num
        return None

    return search(payload)

# ---------- 查询单个目标 ----------
def query_one_target(env, target):
    """查询单个房间的电费"""
    url = env.get('ELEC_API_URL', 'http://wxykt.tiangong.edu.cn/charge/feeitem/getThirdData')
    headers = {
        'Content-Type': 'application/x-www-form-urlencoded',
        'Accept': 'application/json, text/plain, */*',
        'Authorization': env.get('AUTHORIZATION', 'Basic Y2hhcmdlOmNoYXJnZV9zZWNyZXQ='),
        'Referer': env.get('REFERER', 'http://wxykt.tiangong.edu.cn/charge-app/'),
        'Origin': env.get('ORIGIN', 'http://wxykt.tiangong.edu.cn'),
        'Accept-Language': env.get('ACCEPT_LANGUAGE', 'zh-CN,zh;q=0.9'),
        'User-Agent': env.get('USER_AGENT', 'Mozilla/5.0 (Windows NT 10.0; WOW64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/129.0.6668.101 Safari/537.36'),
    }
    if env.get('SYNJONES_AUTH_TOKEN'):
        headers['synjones-auth'] = f"bearer {env['SYNJONES_AUTH_TOKEN']}"
    if env.get('REQUEST_COOKIE'):
        headers['Cookie'] = env['REQUEST_COOKIE']

    # 构建请求体（优先使用 target 中的参数，否则用环境变量默认值）
    body = {
        'feeitemid': target.get('feeitemid') or env.get('FEEITEM_ID', '428'),
        'type': target.get('type') or env.get('FEE_TYPE', 'IEC'),
        'level': target.get('level') or env.get('FEE_LEVEL', '4'),
        'campus': target.get('campus') or env.get('CAMPUS', '天津工业大学&天津工业大学'),
        'building': target.get('building') or env.get('BUILDING', '20161008184448464922&西苑7号楼'),
        'floor': target.get('floor') or env.get('FLOOR', '6&6层'),
        'room': target.get('room') or env.get('ROOM', '20161009111811624619&1栋609'),
    }
    # 确保值为字符串
    for k in body:
        body[k] = str(body[k])

    try:
        resp = requests.post(url, headers=headers, data=body, timeout=15)
        resp.raise_for_status()
        data = resp.json()
    except Exception as e:
        return {
            'ok': False,
            'target': target,
            'error': str(e),
        }

    # 检查业务状态码
    code = data.get('code')
    if code != 200:
        return {
            'ok': False,
            'target': target,
            'error': f"业务错误 {code}: {data.get('msg','')}",
            'payload': data,
        }

    # 检查是否返回不可用信息
    show_info = data.get('map', {}).get('showData', {}).get('信息')
    if show_info and any(k in show_info for k in ['暂时无法', '稍后再试', '未知异常', '联系管理员']):
        return {
            'ok': False,
            'target': target,
            'error': f"电表不可用: {show_info}",
            'payload': data,
        }

    # 提取余额
    balance_path = target.get('balancePath') or env.get('BALANCE_PATH')
    balance = extract_balance(data, balance_path)

    return {
        'ok': True,
        'target': target,
        'balance': balance,
        'payload': data,
    }

# ---------- 判断是否应该通知 ----------
def should_notify(env, query_result, force_notify=False):
    mode = env.get('NOTIFY_MODE', 'always').lower()
    threshold = parse_number(env.get('LOW_BALANCE_THRESHOLD'))

    if force_notify:
        return True, 'force_notify'

    if mode == 'never':
        return False, 'mode_never'

    balance = query_result.get('balance')
    if mode == 'low_balance':
        if balance is None:
            return False, 'balance_unknown'
        if threshold is None:
            return False, 'threshold_missing'
        return balance <= threshold, f"low_balance ({balance} <= {threshold})"

    # always 或其他情况
    return True, 'mode_always'

# ---------- 发送企业微信通知 ----------
def send_wecom(webhook_url, message):
    if not webhook_url:
        return {'channel': 'wecom', 'ok': False, 'error': 'no webhook'}
    try:
        resp = requests.post(webhook_url, json={
            'msgtype': 'text',
            'text': {'content': message}
        }, timeout=10)
        resp.raise_for_status()
        return {'channel': 'wecom', 'ok': True, 'status': resp.status_code}
    except Exception as e:
        return {'channel': 'wecom', 'ok': False, 'error': str(e)}

# ---------- 构建消息 ----------
def build_message(query_result, source, queried_at, reason):
    target = query_result.get('target', {})
    building_name = query_result.get('payload', {}).get('map', {}).get('data', {}).get('buildingName', '未知楼栋')
    room_name = query_result.get('payload', {}).get('map', {}).get('data', {}).get('roomName', '未知房间')
    title = f"{building_name}{room_name}电费查询结果"
    balance_text = f"{query_result['balance']}度" if query_result.get('balance') is not None else "未识别"
    return f"{title}\n来源: {source}\n时间: {queried_at}\n剩余电量: {balance_text}\n触发原因: {reason}"

def build_error_message(target, error, source, queried_at):
    # 简单显示目标标识
    target_name = target.get('name') or target.get('id') or '未知目标'
    return f"{target_name}电费查询失败\n来源: {source}\n时间: {queried_at}\n错误: {error}"

# ---------- 主流程 ----------
def main():
    # 所有配置从环境变量获取（GitHub Secrets）
    env = os.environ.copy()

    # 必须的凭证
    required = ['SYNJONES_AUTH_TOKEN', 'REQUEST_COOKIE']
    missing = [r for r in required if not env.get(r)]
    if missing:
        print(f"缺少必要环境变量: {missing}")
        sys.exit(1)

    # 解析目标列表
    targets_json = env.get('TARGETS_JSON')
    if targets_json:
        try:
            targets = json.loads(targets_json)
            if not isinstance(targets, list) or len(targets) == 0:
                print("TARGETS_JSON 不是有效的非空数组，使用单目标")
                targets = [{}]  # 使用默认参数
        except json.JSONDecodeError:
            print("TARGETS_JSON 解析失败，使用单目标")
            targets = [{}]
    else:
        targets = [{}]  # 单目标，使用环境变量中的默认参数

    # 查询间隔（秒）
    interval = parse_number(env.get('TARGET_QUERY_INTERVAL_SECONDS')) or 60
    if interval < 0:
        interval = 0

    # 企业微信 Webhook
    wecom_webhook = env.get('WECOM_WEBHOOK')

    source = 'github_action'
    queried_at = format_utc8()

    results = []
    for idx, target in enumerate(targets):
        # 为每个目标分配 id（如果没有）
        if 'id' not in target:
            target['id'] = f"target_{idx+1}"

        print(f"查询目标 {target.get('id')} ...")
        qres = query_one_target(env, target)
        results.append(qres)

        # 通知决策
        if qres['ok']:
            notify, reason = should_notify(env, qres, force_notify=False)
            if notify:
                msg = build_message(qres, source, queried_at, reason)
                notify_res = send_wecom(wecom_webhook, msg)
                if notify_res['ok']:
                    print(f"已发送通知给 {target['id']}")
                else:
                    print(f"通知发送失败: {notify_res.get('error')}")
            else:
                print(f"目标 {target['id']} 无需通知 (原因: {reason})")
        else:
            # 查询失败，是否发送错误通知？
            notify_on_error = env.get('NOTIFY_ON_ERROR', 'true').lower() in ('1', 'true', 'yes', 'on')
            if notify_on_error:
                err_msg = build_error_message(target, qres.get('error'), source, queried_at)
                notify_res = send_wecom(wecom_webhook, err_msg)
                if notify_res['ok']:
                    print(f"已发送错误通知给 {target['id']}")
                else:
                    print(f"错误通知发送失败: {notify_res.get('error')}")
            else:
                print(f"目标 {target['id']} 查询失败，未发送通知: {qres.get('error')}")

        # 间隔（最后一个不等待）
        if idx < len(targets) - 1 and interval > 0:
            time.sleep(interval)

    # 汇总打印
    success = sum(1 for r in results if r['ok'])
    print(f"查询完成，成功 {success}/{len(results)}")

if __name__ == '__main__':
    main()
