import os
import requests
import json
import re
from urllib.parse import urlencode

# 电量报警阈值（单位：度）
ALARM_THRESHOLD = float(os.getenv("ALARM_THRESHOLD", "10"))

def send_wecom(message):
    """通过企业微信机器人发送消息"""
    webhook_url = os.getenv("WECOM_WEBHOOK_URL")
    if not webhook_url:
        print("未设置企业微信 Webhook URL，跳过通知")
        return

    payload = {
        "msgtype": "text",
        "text": {
            "content": message
        }
    }
    try:
        resp = requests.post(webhook_url, json=payload, timeout=5)
        resp.raise_for_status()
        result = resp.json()
        if result.get("errcode") == 0:
            print("企业微信通知发送成功")
        else:
            print(f"企业微信通知发送失败：{result}")
    except Exception as e:
        print(f"企业微信通知异常：{e}")

def main():
    # 从环境变量读取配置（GitHub Secrets）
    basic_auth = os.getenv("BASIC_AUTH")
    synjones_auth = os.getenv("SYNJONES_AUTH")
    user_id = os.getenv("USER_ID")
    tgc = os.getenv("TGC")

    # 请求体参数（可硬编码或从环境变量读取）
    payload = {
        "feeitemid": os.getenv("FEE_ITEM_ID", "428"),
        "type": os.getenv("TYPE", "IEC"),
        "level": os.getenv("LEVEL", "4"),
        "campus": os.getenv("CAMPUS", "天津工业大学&天津工业大学"),
        "building": os.getenv("BUILDING", "20161008184448464922&西苑7号楼"),
        "floor": os.getenv("FLOOR", "6&6层"),
        "room": os.getenv("ROOM", "20161009111811827231&1栋608")
    }

    # URL 编码请求体
    encoded_payload = urlencode(payload)

    # 构造请求头
    headers = {
        "Authorization": basic_auth,
        "synjones-auth": synjones_auth,
        "Cookie": f'TGC="{tgc}"; UserId={user_id}',
        "Content-Type": "application/x-www-form-urlencoded",
        "User-Agent": "Mozilla/5.0 (Linux; Android 16; V2408A Build/BQ2A.250705.001-BP2A.250605.031.A3_V000L1; wv) AppleWebKit/537.36 (KHTML, like Gecko) Version/4.0 Chrome/138.0.7204.180 Mobile Safari/537.36 XWEB/1380275 MMWEBSDK/20250202 MMWEBID/3998 wxwork/5.0.6 MicroMessenger/7.0.1 NetType/WIFI Language/zh Lang/zh ColorScheme/Light wwmver/3.26.506.647",
        "Origin": "http://wxykt.tiangong.edu.cn",
        "Referer": "http://wxykt.tiangong.edu.cn/charge-app/",
        "X-Requested-With": "com.tencent.wework",
        "Accept": "application/json, text/plain, */*",
        "Accept-Language": "zh-CN,zh;q=0.9,en-US;q=0.8,en;q=0.7"
    }

    url = "http://wxykt.tiangong.edu.cn/charge/feeitem/getThirdData"
    message = ""
    electricity = None

    try:
        response = requests.post(url, headers=headers, data=encoded_payload, timeout=10)
        response.raise_for_status()
        data = response.json()

        if data.get("code") == 200:
            show_data = data["map"]["showData"]["信息"]
            print(f"查询成功：{show_data}")

            # 提取电量数值（例如：55.66）
            match = re.search(r"剩余购电量:([\d.]+)度", show_data)
            if match:
                electricity = float(match.group(1))
                print(f"当前剩余电量：{electricity} 度")
                if electricity < ALARM_THRESHOLD:
                    # 低电量报警
                    message = f"⚠️ 低电量报警！当前剩余电量仅 {electricity} 度（低于 {ALARM_THRESHOLD} 度）\n详细信息：{show_data}"
                else:
                    message = f"【电费提醒】当前剩余电量：{electricity} 度\n详细信息：{show_data}"
            else:
                message = f"【电费提醒】查询成功但未提取到电量：{show_data}"
        else:
            error_msg = f"查询失败，返回码：{data.get('code')}，信息：{data.get('msg')}"
            print(error_msg)
            message = f"【电费提醒】{error_msg}"

    except Exception as e:
        error_msg = f"请求异常：{e}"
        print(error_msg)
        message = f"【电费提醒】{error_msg}"

    # 发送企业微信通知（如果 message 不为空）
    if message:
        send_wecom(message)
    else:
        print("没有消息可发送")

if __name__ == "__main__":
    main()
