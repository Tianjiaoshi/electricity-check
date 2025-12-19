# -*- coding: utf-8 -*-
# 导入所需的库
import requests
import json
import time
import os
import re

# --- 1. 配置区域---
# 从环境变量（GitHub Secrets）中加载所有敏感信息
WECHAT_WORK_WEBHOOK = os.environ.get('WECHAT_WORK_WEBHOOK')
JSESSIONID = os.environ.get('JSESSIONID')

# 检查所有必需的密钥（Secrets）是否已成功加载
if not all([WECHAT_WORK_WEBHOOK, JSESSIONID]):
    print("❌ 错误：缺少一个或多个必要的环境变量（Secrets）。")
    print("请在GitHub仓库的 Secrets 设置中配置 WECHAT_WORK_WEBHOOK 和 JSESSIONID。")
    exit(1)

# 打印配置信息（调试用）
print(f"✅ 配置加载成功")
print(f"📱 企业微信Webhook: {WECHAT_WORK_WEBHOOK[:50]}...")
print(f"🔑 JSESSIONID: {JSESSIONID[:10]}...")

# --- 要查询的寝室列表 ---
DORM_LIST = [
 
    {
        "dorm_name": "西苑7号楼 1栋608",
        "buildingid": "20161008184448464922",
        "building": "西苑7号楼",
        "floorid": "6",
        "floor": "6层",
        "roomid": "20161009111811827231",
        "room": "1栋608"
    }
    # 可继续添加更多寝室
]

def get_electricity_info(dorm_config):
    """查询指定寝室的电费信息"""
    url = "http://wxjdf.tiangong.edu.cn:9910/web/Common/Tsm.html"
    headers = {
        'Host': 'wxjdf.tiangong.edu.cn:9910',
        'Connection': 'keep-alive',
        'Accept': 'application/json, text/javascript, */*; q=0.01',
        'X-Requested-With': 'XMLHttpRequest',
        'User-Agent': 'Mozilla/5.0 (Linux; Android 12; SM-F926U Build/V417IR; wv) AppleWebKit/537.36 (KHTML, like Gecko) Version/4.0 Chrome/101.0.4951.61 Safari/537.36 MMWEBID/2279 MicroMessenger/8.0.58.2841(0x28003A52) WeChat/arm64 Weixin NetType/WIFI Language/zh_CN ABI/arm64',
        'Content-Type': 'application/x-www-form-urlencoded; charset=UTF-8',
        'Origin': 'http://wxjdf.tiangong.edu.cn:9910',
        'Referer': 'http://wxjdf.tiangong.edu.cn:9910/web/common/checkEle.html',
        'Cookie': f'JSESSIONID={JSESSIONID}',
    }

    # 构建请求体
    query_payload = {
        "query_elec_roominfo": {
            "aid": "0030000000006001",
            "account": "26577",
            "room": {"roomid": dorm_config["roomid"], "room": dorm_config["room"]},
            "floor": {"floorid": dorm_config["floorid"], "floor": dorm_config["floor"]},
            "area": {"area": "天津工业大学", "areaname": "天津工业大学"},
            "building": {"buildingid": dorm_config["buildingid"], "building": dorm_config["building"]}
        }
    }
    
    jsondata_string = json.dumps(query_payload, separators=(',', ':'))
    payload = {
        'jsondata': jsondata_string,
        'funname': 'synjones.onecard.query.elec.roominfo',
        'json': 'true'
    }

    print(f"🚀 正在查询: {dorm_config['dorm_name']}")
    try:
        response = requests.post(url, headers=headers, data=payload, timeout=15)
        print(f"📡 响应状态码: {response.status_code}")
        
        # 尝试解析JSON响应
        try:
            response_data = response.json()
            print(f"📊 响应JSON: {json.dumps(response_data, ensure_ascii=False)[:200]}...")
            
            # 检查是否有错误信息
            errmsg = response_data.get("query_elec_roominfo", {}).get("errmsg", "")
            print(f"📝 服务器消息: {errmsg}")
            
            # 尝试匹配剩余电量
            success_match = re.search(r'剩余购电量:(\d+\.?\d*)度', errmsg)
            
            if success_match:
                result = {
                    "dorm_name": dorm_config['dorm_name'],
                    "remaining_kwh": success_match.group(1),
                    "raw_response": errmsg,
                    "status": "success"
                }
                print(f"✅ 查询成功: {result['dorm_name']} 剩余电量: {result['remaining_kwh']}度")
                return result, None
            else:
                # 尝试其他可能的返回格式
                fallback_match = re.search(r'剩余金额:(\d+\.?\d*)元', errmsg)
                if fallback_match:
                    result = {
                        "dorm_name": dorm_config['dorm_name'],
                        "remaining_kwh": fallback_match.group(1) + "元",
                        "raw_response": errmsg,
                        "status": "success"
                    }
                    print(f"✅ 查询成功: {result['dorm_name']} 剩余金额: {result['remaining_kwh']}")
                    return result, None
                
                # 检查是否是session过期
                if "session" in errmsg.lower() or "登录" in errmsg.lower():
                    error_msg = "JSESSIONID可能已过期，请重新获取"
                else:
                    error_msg = f"查询失败，服务器消息: {errmsg}"
                
                print(f"❌ {error_msg}")
                return None, error_msg
                
        except json.JSONDecodeError as e:
            print(f"❌ JSON解析错误: {e}")
            print(f"📄 原始响应: {response.text[:500]}")
            return None, f"服务器响应格式错误: {response.text[:100]}..."

    except requests.exceptions.Timeout:
        return None, "请求超时，请稍后重试"
    except requests.exceptions.RequestException as e:
        return None, f"网络请求异常: {e}"

def send_to_wechat_work(content, msg_type="markdown", mentioned_list=None, mentioned_mobile_list=None):
    """
    发送消息到企业微信机器人
    
    参数:
    - content: 消息内容，对于markdown是字符串，对于text是字典
    - msg_type: 消息类型，支持 "text", "markdown", "news"
    - mentioned_list: @用户列表（用户ID）
    - mentioned_mobile_list: @用户列表（手机号）
    """
    print(f"🤖 正在准备发送企业微信通知...")
    
    payload = {
        "msgtype": msg_type,
    }
    
    if msg_type == "markdown":
        payload["markdown"] = {
            "content": content
        }
    elif msg_type == "text":
        if isinstance(content, str):
            content = {"content": content}
        payload["text"] = content
        if mentioned_list:
            payload["text"]["mentioned_list"] = mentioned_list
        if mentioned_mobile_list:
            payload["text"]["mentioned_mobile_list"] = mentioned_mobile_list
    elif msg_type == "news":
        payload["news"] = content
    
    headers = {
        'Content-Type': 'application/json'
    }
    
    try:
        print(f"📤 发送请求到企业微信...")
        response = requests.post(WECHAT_WORK_WEBHOOK, 
                                headers=headers, 
                                data=json.dumps(payload, ensure_ascii=False), 
                                timeout=10)
        print(f"📥 企业微信响应状态码: {response.status_code}")
        result = response.json()
        
        if result.get("errcode") == 0:
            print("✅ 企业微信消息发送成功！")
        else:
            print(f"❌ 企业微信消息发送失败: {result.get('errmsg')}")
            # 如果是webhook无效，给出提示
            if result.get("errcode") == 93000:
                print("⚠️ Webhook可能已失效，请重新创建机器人")
        return result
    except Exception as e:
        print(f"❌ 发送企业微信消息时出现异常: {e}")
        return None

def send_test_message():
    """发送测试消息到企业微信"""
    print("🧪 发送测试消息...")
    
    # 测试markdown消息
    test_content = "## 🧪 测试消息\n\n这是一个来自电费查询系统的测试消息\n\n**当前时间**: " + time.strftime('%Y-%m-%d %H:%M:%S') + "\n\n<font color=\"info\">✅ 机器人连接正常</font>"
    
    result = send_to_wechat_work(test_content, "markdown")
    
    if result and result.get("errcode") == 0:
        print("✅ 测试消息发送成功，机器人配置正确！")
        return True
    else:
        print("❌ 测试消息发送失败，请检查配置")
        return False

# --- 主程序入口 ---
if __name__ == "__main__":
    print("=" * 60)
    print("🔋 电费查询机器人 v2.0")
    print("=" * 60)
    
    # 首先发送测试消息
    if not send_test_message():
        print("⚠️ 测试消息发送失败，但将继续尝试查询电费...")
    
    time.sleep(2)  # 等待一下
    
    all_results = []
    all_errors = []
    
    print(f"\n📊 开始查询 {len(DORM_LIST)} 个寝室...")
    
    for i, dorm in enumerate(DORM_LIST):
        print(f"\n{'='*40}")
        print(f"🏠 查询 [{i+1}/{len(DORM_LIST)}]: {dorm['dorm_name']}")
        
        result, error = get_electricity_info(dorm)
        
        if result:
            all_results.append(result)
            print(f"✅ 成功 - 剩余: {result['remaining_kwh']}")
        else:
            all_errors.append(f"{dorm['dorm_name']}: {error}")
            print(f"❌ 失败: {error}")
        
        # 如果不是最后一个，等待一下再查询下一个
        if i < len(DORM_LIST) - 1:
            print(f"⏳ 等待2秒后查询下一个...")
            time.sleep(2)
    
    current_time = time.strftime('%Y-%m-%d %H:%M:%S')
    
    # 构建汇总消息
    if all_results:
        print("\n📋 构建汇总消息...")
        
        # 创建markdown格式的消息
        markdown_content = f"## 🔋 电费查询报告\n\n"
        markdown_content += f"**查询时间**：{current_time}\n\n"
        
        # 添加寝室详情表格
        markdown_content += "### 📊 查询结果\n"
        
        # 统计低电量寝室
        low_power_count = 0
        urgent_count = 0
        
        for result in all_results:
            try:
                # 提取数字部分
                import re
                num_match = re.search(r'(\d+\.?\d*)', result['remaining_kwh'])
                if num_match:
                    kwh = float(num_match.group(1))
                    if kwh < 3:
                        urgent_count += 1
                        status_icon = "🔴"
                        status_text = "严重不足"
                        status_color = "<font color=\"warning\">严重不足</font>"
                    elif kwh < 10:
                        low_power_count += 1
                        status_icon = "🟡"
                        status_text = "电量不足"
                        status_color = "<font color=\"warning\">电量不足</font>"
                    else:
                        status_icon = "🟢"
                        status_text = "电量充足"
                        status_color = "<font color=\"info\">电量充足</font>"
                else:
                    status_icon = "⚪"
                    status_text = "未知"
                    status_color = "未知"
            except (ValueError, AttributeError):
                status_icon = "⚪"
                status_text = "未知"
                status_color = "未知"
            
            markdown_content += f"{status_icon} **{result['dorm_name']}**：**{result['remaining_kwh']}**（{status_color}）\n\n"
        
        # 添加统计信息
        markdown_content += f"### 📈 统计信息\n"
        markdown_content += f"- 查询寝室数：{len(all_results)} 个\n"
        
        if urgent_count > 0:
            markdown_content += f"- <font color=\"warning\">严重低电量：{urgent_count} 个（<3度）</font>\n"
        if low_power_count > 0:
            markdown_content += f"- <font color=\"warning\">低电量：{low_power_count} 个（<10度）</font>\n"
        
        # 添加失败信息
        if all_errors:
            markdown_content += f"\n### ⚠️ 查询失败\n"
            for error in all_errors:
                markdown_content += f"- {error}\n"
        
        # 添加建议
        markdown_content += f"\n### 💡 温馨提示\n"
        
        if urgent_count > 0:
            markdown_content += f"<font color=\"warning\">**🚨 紧急提醒**：有 {urgent_count} 个寝室电量严重不足（<3度），请立即充电！</font>\n\n"
        elif low_power_count > 0:
            markdown_content += f"<font color=\"warning\">**⚠️ 提醒**：有 {low_power_count} 个寝室电量不足（<10度），建议及时充电。</font>\n\n"
        else:
            markdown_content += f"所有寝室电量充足，请放心使用。\n\n"
        
        markdown_content += f"---\n"
        markdown_content += f"<font color=\"comment\">⚡ 自动电费查询系统 | {current_time}</font>"
        
        # 发送主消息
        print("📤 发送主报告到企业微信...")
        send_result = send_to_wechat_work(markdown_content, "markdown")
        
        # 如果有严重低电量的宿舍，再单独发送紧急通知
        urgent_dorms = []
        for d in all_results:
            try:
                num_match = re.search(r'(\d+\.?\d*)', d['remaining_kwh'])
                if num_match and float(num_match.group(1)) < 3:
                    urgent_dorms.append(d)
            except:
                pass
        
        if urgent_dorms:
            print("🚨 检测到严重低电量寝室，发送紧急通知...")
            time.sleep(3)  # 等待一下再发第二条消息
            
            # 构建紧急通知
            urgent_content = f"## 🚨 紧急电量预警\n\n"
            urgent_content += f"**以下寝室电量严重不足，请立即处理：**\n\n"
            
            for dorm in urgent_dorms:
                urgent_content += f"🔴 **{dorm['dorm_name']}**：仅剩 **{dorm['remaining_kwh']}** ！\n\n"
            
            urgent_content += f"**⚠️ 可能随时断电，请尽快充值！**\n\n"
            urgent_content += f"---\n"
            urgent_content += f"<font color=\"comment\">紧急提醒 | {current_time}</font>"
            
            send_to_wechat_work(urgent_content, "markdown")
            
            # 可以额外发送一个text消息用于@所有人
            urgent_text = {
                "content": f"【紧急通知】有{len(urgent_dorms)}个寝室电量严重不足（<3度），可能随时断电，请相关同学立即处理！",
                "mentioned_list": ["@all"]  # @所有人
            }
            time.sleep(2)
            print("📢 发送@所有人的紧急通知...")
            send_to_wechat_work(urgent_text, "text")
    
    elif all_errors:
        # 全部失败的情况
        print("❌ 所有查询都失败了，发送错误报告...")
        error_content = f"## ❌ 电费查询失败\n\n"
        error_content += f"**时间**：{current_time}\n\n"
        error_content += f"所有寝室查询都失败了：\n\n"
        
        for error in all_errors:
            error_content += f"- {error}\n"
        
        error_content += f"\n### 🔧 可能原因\n"
        error_content += f"1. **JSESSIONID 已过期**（最常见）\n"
        error_content += f"2. 学校服务器维护中\n"
        error_content += f"3. 网络连接问题\n"
        error_content += f"4. 寝室参数配置错误\n"
        
        error_content += f"\n### 💡 解决方案\n"
        error_content += f"1. 重新获取 JSESSIONID\n"
        error_content += f"2. 稍后重试\n"
        error_content += f"3. 检查寝室配置信息\n"
        
        error_content += f"\n---\n"
        error_content += f"<font color=\"comment\">⚡ 自动电费查询系统 | {current_time}</font>"
        
        send_to_wechat_work(error_content, "markdown")
    else:
        print("⚠️ 没有查询到任何结果，也没有错误信息")
    
    print("\n" + "="*60)
    print(f"🏁 任务执行完成！")
    print("="*60)
