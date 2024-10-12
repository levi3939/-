import re
import requests
import time
import tkinter as tk
from tkinter import ttk, messagebox, scrolledtext, simpledialog
import pyperclip
import mysql.connector
from mysql.connector import Error
import os
from datetime import datetime
import overpy
import logging
from openai import OpenAI
import json

# 创建主窗口
root = tk.Tk()
root.title("订单处理系统")

# 设置窗口大小可调整和全屏自适应
root.geometry("800x600")
root.grid_columnconfigure(0, weight=1)
root.grid_rowconfigure(0, weight=1)

# 创建logs文件夹(如果不存在)
if not os.path.exists('logs'):
    os.makedirs('logs')

# 生成日志文件名(使用当前日期和时间)
log_filename = f"logs/app_log_{datetime.now().strftime('%Y%m%d_%H%M%S')}.log"

# 配置日志
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler(log_filename, encoding='utf-8'),
        logging.StreamHandler()  # 这将保持控制台输出
    ]
)

API_KEY = 'rPEhmHF9qxMJib2cmKD7rmvyTSVWA8DH'  # 请确保使用正确的API密钥

# 上海区名列表,用于辅助地址识别
SHANGHAI_DISTRICTS = [
    "黄浦", "徐汇", "长宁", "静安", "普陀", "虹口", "杨浦", "闵行", "宝山", "嘉定", 
    "浦东", "金山", "松江", "青浦", "奉贤", "崇明","黄浦区", "徐汇区", "长宁区", "静安区", 
    "普陀区", "虹口区", "杨浦区", "闵行区", "宝山区", "嘉定区", 
    "浦东新区", "金山区", "松江区", "青浦区", "奉贤区", "崇明区"
]

# 无效信息列表,用于清理订单文本
INVALID_INFO = [
    r"上海专职订单",
    r"有需要请加微信:xuecheng11003\(高提成诚招代理出单",
    r"今日新单加急出",
    # 可以继续添加其他无效信息模式
]

# 订单格式定义
ORDER_FORMATS = {
    'format1': r'上海\d+',
    'format2': r'(?:' + '|'.join(SHANGHAI_DISTRICTS) + r').*',
    'format3': r'【.*】',
    'format4': r'SH\d+',
    # 可以继续添加其他订单格式
}

# 添加DeepSeek API配置
DEEPSEEK_API_KEY = 'sk-b830f7dd0ad04f9990ace700d7cbeb7f'
client = OpenAI(api_key=DEEPSEEK_API_KEY, base_url="https://api.deepseek.com")

def remove_invalid_info(text):
    """移除无效信息"""
    original_length = len(text)
    for pattern in INVALID_INFO:
        matches = re.findall(pattern, text)
        for match in matches:
            logging.info(f"删除无关信息: {match}")
        text = re.sub(pattern, '', text)
    
    cleaned_length = len(text)
    if original_length != cleaned_length:
        logging.info(f"总共删除了 {original_length - cleaned_length} 个字符的无关信息")
    
    return text.strip()

def identify_order_format(order_text):
    """识别订单格式"""
    for format_name, pattern in ORDER_FORMATS.items():
        if re.match(pattern, order_text):
            return format_name
    return 'unknown'

def parse_order_format1(order_text):
    """解析格式1的订单"""
    info = {'full_text': order_text}
    lines = order_text.split('\n')
    for line in lines:
        if line.startswith('地址'):
            info['address'] = line.split('★', 1)[1].strip()
            break
    return info

def parse_order_format2(order_text):
    """解析格式2的订单"""
    info = {'full_text': order_text}
    for district in SHANGHAI_DISTRICTS:
        if order_text.startswith(district):
            info['address'] = order_text.split(' ', 1)[0]
            break
    return info

def parse_order_format3(order_text):
    """解析格式3的订单"""
    info = {'full_text': order_text}
    match = re.search(r'【(.+?)】', order_text)
    if match:
        info['address'] = match.group(1)
    return info

def parse_order_format4(order_text):
    """解析格式4的订单"""
    info = {'full_text': order_text}
    lines = order_text.split('\n')
    for line in lines:
        if line.startswith('联系地址'):
            info['address'] = line.split('：', 1)[1].strip()
            break
    return info

def extract_address(order: str):
    """提取地址"""
    # 匹配完整地址模式
    full_address_pattern = r'(?:' + '|'.join(SHANGHAI_DISTRICTS) + r')[区]?.*?(?:路|街|巷|弄|号|楼|园|苑|城|湾|站|小区|大厦|公寓|村|花园|广场|学校|庭|隔壁)'
    full_match = re.search(full_address_pattern, order)
    if full_match:
        return full_match.group()

    # 匹配区名开头的地址
    district_pattern = r'(?:' + '|'.join(SHANGHAI_DISTRICTS) + r')[区]?.*?(?:\S+路|\S+街|\S+巷|\S+弄|\S+号|\S+楼|\S+园|\S+苑|\S+城|\S+湾|\S+站|\S+小区|\S+大厦|\S+公寓|\S+村|\S+花园|\S+广场|\S+学校)'
    district_match = re.search(district_pattern, order)
    if district_match:
        return district_match.group()

    # 匹配包含路名的地址
    road_pattern = r'[\u4e00-\u9fa5]{2,}(?:路|街|巷|弄)(?:\d+号?)?'
    road_match = re.search(road_pattern, order)
    if road_match:
        return road_match.group()

    # 如果所尝试都失败，返回None
    return None

def get_geocode(address: str):
    logging.info(f"获取地理编码: {address}")
    try:
        connection = mysql.connector.connect(
            host='localhost',
            database='address_cache',
            user='root',
            password='232435'
        )
        cursor = connection.cursor()
        
        cursor.execute("SELECT latitude, longitude, uid FROM addresses WHERE address = %s", (address,))
        result = cursor.fetchone()
        if result:
            return result  # 返回 (纬度, 经度, uid)

        url = f"http://api.map.baidu.com/geocoding/v3/"
        params = {
            'address': address,
            'output': 'json',
            'ak': API_KEY,
            'city': '上海市'  # 添加这一行
        }
        response = requests.get(url, params=params, timeout=10)
        data = response.json()
        if data['status'] == 0 and 'result' in data and 'location' in data['result']:
            lat = data['result']['location']['lat']
            lng = data['result']['location']['lng']
            
            # ���证坐标是否在上海范围内
            if 30.7 <= lat <= 31.5 and 120.9 <= lng <= 122.1:
                uid = data['result'].get('uid', '')
                
                cursor.execute("INSERT INTO addresses (address, latitude, longitude, uid) VALUES (%s, %s, %s, %s)",
                                 (address, lat, lng, uid))
                connection.commit()
                return lat, lng, uid
            else:
                return None
        
        return None
    except Error as e:
        logging.error(f"数据库操作错误: {str(e)}")
        return None
    except requests.RequestException as e:
        logging.error(f"请求地理编码API时出错: {str(e)}")
        return None
    finally:
        if connection and connection.is_connected():
            cursor.close()
            connection.close()


def get_transit_route(lat_lng_origin, lat_lng_destination, origin_uid=None, destination_uid=None, max_retries: int = 3):
    """
    调用百度地图公交路线规划API，获取从origin到destination的详细路线。
    """
    url = "https://api.map.baidu.com/directionlite/v1/transit"
    params = {
        'origin': f"{lat_lng_origin[0]},{lat_lng_origin[1]}",  # 纬度在前，经度在后
        'destination': f"{lat_lng_destination[0]},{lat_lng_destination[1]}",  # 纬度在前，经度在后
        'ak': API_KEY,
        'coord_type': 'bd09ll',
        'ret_coordtype': 'bd09ll',
    }
    
    # 如果提供origin_uid，则添加数
    if origin_uid:
        params['origin_uid'] = origin_uid
    
    # 如果提供了destination_uid，则添加到参数中
    if destination_uid:
        params['destination_uid'] = destination_uid

    for attempt in range(max_retries):
        try:
            response = requests.get(url, params=params, timeout=10)
            data = response.json()
            if data['status'] == 0 and 'result' in data and 'routes' in data['result']:
                best_route = min(data['result']['routes'], key=lambda x: x.get('duration', float('inf')))
                duration = best_route.get('duration', 0)
                distance = best_route.get('distance', 0)
                return format_route(best_route)
        except (requests.exceptions.RequestException, ValueError, KeyError) as e:
            pass
    return None




def process_orders_with_ai(order_input: str):
    """
    使用DeepSeek V2.5大模型处理订单
    """
    prompt = f"""
    请处理以下订单信息:
    1. 智能去除无关信息
    2. 智能分割订单串为单独的订单
    3. 智能提取每个订单的订单号(如果没有就用"无")、地址、订单原文
    4. 以JSON格式返回结果,格式为:
    [
        {{
            "order_id": "订单号",
            "address": "地址",
            "full_text": "订单原文"
        }},
        ...
    ]

    订单信息:
    {order_input}
    """

    try:
        response = client.chat.completions.create(
            model="deepseek-chat",
            messages=[
                {"role": "system", "content": "你是一个智能订单处理助手。"},
                {"role": "user", "content": prompt}
            ],
            temperature=0.7,
            max_tokens=2000
        )
        
        result = response.choices[0].message.content
        logging.info(f"AI返回的原始结果: {result}")
 
        # 清理结果
        result = re.sub(r'```json\n?|\n?```', '', result).strip()
        result = result.replace('\n', '').replace('\r', '')
        
        try:
            parsed_result = json.loads(result)
            logging.info("AI返回的结果是有效的JSON格式")
            return parsed_result
        except json.JSONDecodeError as e:
            logging.error(f"AI返回的结果不是有效的JSON格式: {str(e)}")
            logging.error(f"问题字符串: {result[max(0, e.pos-20):min(len(result), e.pos+20)]}")
            logging.error(f"错误位置: {e.pos}")
       
            # 尝试手动解析
            orders = []
            for i, line in enumerate(result.split('},{')):
                if line.strip():
                    try:
                        # 确保每个部分都是完整的JSON对象
                        if i == 0:
                            line = line + '}'
                        elif i == len(result.split('},{')) - 1:
                            line = '{' + line
                        else:
                            line = '{' + line + '}'
                        
                        order = json.loads(line)
                        orders.append(order)
                    except json.JSONDecodeError as sub_e:
                        logging.error(f"无法解析第 {i+1} 个订单: {line}")
                        logging.error(f"错误详情: {str(sub_e)}")
                        logging.error(f"问题字符串: {line[max(0, sub_e.pos-20):min(len(line), sub_e.pos+20)]}")
            if orders:
                logging.info(f"手动解析成功，共解析 {len(orders)} 个订单")
                return orders
            return None
    except Exception as e:
        logging.error(f"调用DeepSeek API时出错: {str(e)}")
        return None

def format_route(route):
    """
    格式化路线信息
    """
    formatted_route = []
    total_duration = route.get('duration', 0)
    total_distance = route.get('distance', 0)
    for step in route.get('steps', []):
        if isinstance(step, list):
            for sub_step in step:
                if isinstance(sub_step, dict):
                    vehicle = sub_step.get('vehicle', {})
                    if vehicle.get('type') == 5:  # 步行
                        formatted_route.append(f"步{sub_step.get('distance', 0) / 1000:.1f}公里")
                    elif vehicle.get('type') in [1, 2]:  # 地铁或公交
                        formatted_route.append(f"{vehicle.get('name', '')}从{vehicle.get('start_name', '')}站上车")
                        formatted_route.append(f"到{vehicle.get('end_name', '')}站下车")

    route_str = " > ".join(formatted_route)
    hours, minutes = divmod(total_duration // 60, 60)
    time_str = f"{hours}小时{minutes}分钟" if hours > 0 else f"{minutes}分钟"
    distance_str = f"{total_distance / 1000:.1f}公里"
    return f"{route_str}\n总时间: {time_str}, 总距离: {distance_str}"


def get_best_route_time(origin_address: str, destination_address: str):
    """
    获取从 origin_address 到 destination_address 的最佳通勤路线。
    """
    origin_coords = get_geocode(origin_address)
    destination_coords = get_geocode(destination_address)
    if origin_coords and destination_coords:
        route = get_transit_route(origin_coords, destination_coords)
        if route:
            return route
        else:
            return "无法获取通勤路线"
    return "无法获取地理编码"

def init_db():
    try:
        connection = mysql.connector.connect(
            host='localhost',
            user='root',
            password='232435'
        )
        cursor = connection.cursor()

        # 创建数据库（如果不存在）
        cursor.execute("CREATE DATABASE IF NOT EXISTS address_cache")
        cursor.execute("USE address_cache")

        # 创建地址表（包含uid字段和full_address字段）
        cursor.execute("""
        CREATE TABLE IF NOT EXISTS addresses (
            id INT AUTO_INCREMENT PRIMARY KEY,
            address VARCHAR(255) UNIQUE,
            full_address TEXT,
            latitude DECIMAL(10, 8),
            longitude DECIMAL(11, 8),
            uid VARCHAR(255),
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
        """)

        # 创建订单表
        cursor.execute("""
        CREATE TABLE IF NOT EXISTS orders (
            id INT AUTO_INCREMENT PRIMARY KEY,
            order_id VARCHAR(50) UNIQUE,
            origin VARCHAR(255),
            destination VARCHAR(255),
            full_text TEXT,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
        """)

        connection.commit()
    except Error as e:
        print(f"初始化数据库时出错: {str(e)}")
    finally:
        if connection.is_connected():
            cursor.close()
            connection.close()


def save_to_database(decoded_orders):
    connection = None
    try:
        connection = mysql.connector.connect(
            host='localhost',
            database='address_cache',
            user='root',
            password='232435'
        )
        cursor = connection.cursor()

        for order in decoded_orders:
            # 插入订单到orders表
            cursor.execute("""
            INSERT INTO address_cache.orders (order_id, origin, full_text)
            VALUES (%s, %s, %s)
            """, (order['order_id'], order['address'], order['full_text']))

            # 如果有经纬度信息,插入到addresses表
            if 'latitude' in order and 'longitude' in order:
                cursor.execute("""
                INSERT IGNORE INTO address_cache.addresses (address, latitude, longitude, uid)
                VALUES (%s, %s, %s, %s)
                """, (order['address'], order['latitude'], order['longitude'], order.get('uid', '')))

        connection.commit()
        return "数据已成功保存到数据库"

    except mysql.connector.Error as e:
        if connection:
            connection.rollback()
        return f"保存到数据库时出错: {str(e)}"

    finally:
        if connection and connection.is_connected():
            cursor.close()
            connection.close()


def get_known_addresses_from_db():
    # 从数据库获取已知地址列表的函数
    try:
        connection = mysql.connector.connect(
            host='localhost',
            database='address_cache',
            user='root',
            password='232435'
        )
        cursor = connection.cursor()
        cursor.execute("SELECT address FROM addresses")
        addresses = [row[0] for row in cursor.fetchall()]
        return addresses
    except Error as e:
        print(f"从数据库获取地址时出错: {str(e)}")
        return []
    finally:
        if connection.is_connected():
            cursor.close()
            connection.close()


def recommend_orders(start_address):
    try:
        connection = mysql.connector.connect(
            host='localhost',
            database='address_cache',
            user='root',
            password='232435'
        )
        cursor = connection.cursor()

        # 获取所有订单
        cursor.execute("SELECT order_id, destination, latitude, longitude, full_text FROM orders")
        all_orders = cursor.fetchall()

        if not all_orders:
            return "数据库中没有订单数据"

        recommended_orders = []
        for order in all_orders:
            order_id, destination, lat, lng, full_text = order
            
            # 检查经纬度是否有效
            if not (lat and lng):
                continue

            try:
                route = get_best_route_time(start_address, destination)
                if route and route != "无法获取通勤路线" and route != "无法获取地理编码":
                    # 解析路线时间
                    time_match = re.search(r'总时间: (\d+)小时(\d+)分钟|总时间: (\d+)分钟', route)
                    if time_match:
                        hours = int(time_match.group(1) or 0)
                        minutes = int(time_match.group(2) or time_match.group(3) or 0)
                        total_minutes = hours * 60 + minutes
                        if total_minutes <= 90:  # 1小时30分 = 90分钟
                            recommended_orders.append((total_minutes, order_id, destination, route, full_text))
            except Exception as e:
                print(f"处理订单 {order_id} 时出错: {str(e)}")

        # 按通勤时间排序
        recommended_orders.sort(key=lambda x: x[0])

        # 生成结果字符串
        if recommended_orders:
            result = "\n\n".join([f"订单号: {order_id}\n目的地: {destination}\n通勤路线: {route}\n原始订单: {full_text}" 
                                  for _, order_id, destination, route, full_text in recommended_orders])
        else:
            result = "没有找合条件的订"

        return result

    except Error as e:
        return f"推荐订单时出错: {str(e)}"
    finally:
        if connection and connection.is_connected():
            cursor.close()
            connection.close()


def clean_duplicate_data():
    try:
        connection = mysql.connector.connect(
            host='localhost',
            database='address_cache',
            user='root',
            password='232435'
        )
        cursor = connection.cursor()

        # 记录清理前数据状态
        cursor.execute("SELECT COUNT(*) FROM orders")
        orders_before = cursor.fetchone()[0]
        cursor.execute("SELECT COUNT(*) FROM addresses")
        addresses_before = cursor.fetchone()[0]

        # 清理 orders 表中的重复数据，保留每经纬度组合的最新记录
        cursor.execute('''
            DELETE o1 FROM orders o1
            INNER JOIN orders o2 
            WHERE o1.latitude = o2.latitude 
            AND o1.longitude = o2.longitude
            AND o1.id < o2.id
        ''')
        deleted_orders = cursor.rowcount

        # 清理 addresses 表中的重复数据
        cursor.execute('''
            DELETE a1 FROM addresses a1
            INNER JOIN addresses a2 
            WHERE a1.latitude = a2.latitude 
            AND a1.longitude = a2.longitude
            AND a1.address > a2.address
        ''')
        deleted_addresses = cursor.rowcount

        connection.commit()
        total_deleted = deleted_orders + deleted_addresses

        # 记录清理后的数据状态
        cursor.execute("SELECT COUNT(*) FROM orders")
        orders_after = cursor.fetchone()[0]
        cursor.execute("SELECT COUNT(*) FROM addresses")
        addresses_after = cursor.fetchone()[0]

        return f"清理前：订单数 {orders_before}，地址数 {addresses_before}\n" \
               f"清理后：订单数 {orders_after}，地址数 {addresses_after}\n" \
               f"共清理 {total_deleted} 条重复数据"

    except Error as e:
        return f"清理重复数据时出错: {str(e)}"
    finally:
        if connection and connection.is_connected():
            cursor.close()
            connection.close()


def clean_invalid_data():
    try:
        connection = mysql.connector.connect(
            host='localhost',
            database='address_cache',
            user='root',
            password='232435'
        )
        cursor = connection.cursor()

        # 删除不在上海范围内的坐标
        cursor.execute("""
            DELETE FROM addresses 
            WHERE latitude < 30.7 OR latitude > 31.5 
            OR longitude < 120.9 OR longitude > 122.1
        """)

        connection.commit()
        deleted_count = cursor.rowcount
        return f"已清理 {deleted_count} 条无效数据"

    except Error as e:
        return f"清理无效数据时出错: {str(e)}"
    finally:
        if connection and connection.is_connected():
            cursor.close()
            connection.close()

def get_osm_geocode(address):
    api = overpy.Overpass()
    query = f"""
    [out:json];
    area["name"="上海市"]->.searchArea;
    (
      node["addr:street"~"{address}"](area.searchArea);
      way["addr:street"~"{address}"](area.searchArea);
      relation["addr:street"~"{address}"](area.searchArea);
    );
    out center;
    """
    try:
        result = api.query(query)
        if result.nodes:
            node = result.nodes[0]
            return float(node.lat), float(node.lon), ''
        elif result.ways:
            way = result.ways[0]
            return float(way.center_lat), float(way.center_lon), ''
        elif result.relations:
            relation = result.relations[0]
            return float(relation.center_lat), float(relation.center_lon), ''
    except Exception as e:
        print(f"OSM查询出错: {str(e)}")
    return None

def enhance_address(address):
    # 首先尝试使用百度地图API
    baidu_result = get_geocode(address)
    if baidu_result:
        return baidu_result

    # 如果百度地图API失败，尝试使用OSM数据
    osm_result = get_osm_geocode(address)
    if osm_result:
        return osm_result

    # 如果OSM也失败，尝试使用本地数据库
    local_result = get_local_address(address)
    if local_result:
        return local_result

    # 如果有方法都失败，返回None
    return None

def get_reverse_geocode(lat, lng):
    url = f"http://api.map.baidu.com/reverse_geocoding/v3/"
    params = {
        'location': f"{lat},{lng}",
        'output': 'json',
        'ak': API_KEY
    }
    try:
        response = requests.get(url, params=params, timeout=10)
        data = response.json()
        if data['status'] == 0:
            return data['result']['formatted_address']
    except Exception as e:
        print(f"反向地理编码出错: {str(e)}")
    return None

def get_local_address(address):
    try:
        connection = mysql.connector.connect(
            host='localhost',
            database='address_cache',
            user='root',
            password='232435'
        )
        cursor = connection.cursor()
        
        # 使用模糊匹配查询本地数据库
        cursor.execute("SELECT latitude, longitude, uid FROM addresses WHERE address LIKE %s LIMIT 1", (f"%{address}%",))
        result = cursor.fetchone()
        if result:
            return result  # 返回 (纬度, 经度, uid)
    except Error as e:
        print(f"查询本地数据库时出错: {str(e)}")
    finally:
        if connection and connection.is_connected():
            cursor.close()
            connection.close()
    return None

# 在文件的其他函数定义之后，主程序部分之前添加这两个函数

def on_enter(e):
    e.widget['background'] = 'lightblue'

def on_leave(e):
    e.widget['background'] = 'SystemButtonFace'

def copy_result():
    result = result_text.get("1.0", tk.END).strip()
    if result:
        pyperclip.copy(result)
        messagebox.showinfo("复制成功", "结果已复制到剪贴板")
    else:
        messagebox.showwarning("无结果", "没有可复制的内容")

def reset_fields():
    order_text.delete("1.0", tk.END)
    address_entry.delete(0, tk.END)
    result_text.delete("1.0", tk.END)

def calculate_commute():
    try:
        order_input = order_text.get("1.0", tk.END).strip()
        user_address = address_entry.get().strip()

        if not order_input or not user_address:
            messagebox.showwarning("输入错误", "请输入订单和目标地址")
            return

        # 处理订单
        parsed_orders = process_orders_with_ai(order_input)
        if parsed_orders:
            try:
                # 解码地址
                decoded_orders = decode_addresses(parsed_orders)
                
                # 计算通勤时间
                result = ""
                for order in decoded_orders:
                    route = get_best_route_time(user_address, order['address'])
                    result += f"订单号: {order['order_id']}\n"
                    result += f"目的地: {order['address']}\n"
                    result += f"通勤路线: {route}\n"
                    result += f"原始订单: {order['full_text']}\n\n"

                # 显示结果到输出框
                result_text.delete("1.0", tk.END)
                result_text.insert(tk.END, result)
            except Exception as e:
                messagebox.showerror("错误", f"处理AI返回结果时出错: {str(e)}")
                logging.error(f"处理AI返回结果时出错: {str(e)}")
        else:
            messagebox.showerror("错误", "AI处理订单失败")
            logging.error("AI处理订单失败")
    except Exception as e:
        messagebox.showerror("错误", f"计算过程中出现错误: {str(e)}\n\n请检查输入并重试。如果问题持续存在，请联系技术支持。")
        logging.error(f"计算过程中出现错误: {str(e)}")

# 修改 decode_addresses 函数
def decode_addresses(parsed_orders):
    """
    解码地址获取经纬度信息
    """
    decoded_results = []
    for order in parsed_orders:
        address = order['address']
        geocode = get_geocode(address)
        if geocode:
            lat, lng, uid = geocode
            decoded_results.append({
                'order_id': order['order_id'],
                'address': address,
                'full_text': order['full_text'],
                'latitude': lat,
                'longitude': lng,
                'uid': uid
            })
        else:
            decoded_results.append({
                'order_id': order['order_id'],
                'address': address,
                'full_text': order['full_text'],
                'error': '无法获取地理编码'
            })
    return decoded_results

# copy_recommendation_result 函数保持不变
def copy_recommendation_result():
    result = recommendation_result_text.get("1.0", tk.END).strip()
    if result:
        pyperclip.copy(result)
        messagebox.showinfo("复制成功", "推荐结果已复制到剪贴板")
    else:
        messagebox.showwarning("无结果", "没有可复制的内容")

# 修改GUI部分的函数

def process_and_decode():
    order_input = order_text.get("1.0", tk.END).strip()
    if not order_input:
        messagebox.showwarning("输入错误", "请输入订单信息")
        return

    # 使用AI处理订单
    parsed_orders = process_orders_with_ai(order_input)
    if parsed_orders:
        try:
            # 解码地址
            decoded_orders = decode_addresses(parsed_orders)
            
            # 显示结果
            result = ""
            for order in decoded_orders:
                result += f"订单号: {order['order_id']}\n"
                result += f"地址: {order['address']}\n"
                if 'latitude' in order and 'longitude' in order:
                    result += f"经纬度: {order['latitude']}, {order['longitude']}\n"
                elif 'error' in order:
                    result += f"错误: {order['error']}\n"
                result += f"原文: {order['full_text']}\n\n"

            result_text.delete("1.0", tk.END)
            result_text.insert(tk.END, result)
            
            # 保存解码后的订单信息到全局变量,以便后续保存到数据库
            global current_decoded_orders
            current_decoded_orders = decoded_orders
            
        except Exception as e:
            messagebox.showerror("错误", f"处理AI返回结果时出错: {str(e)}")
            logging.error(f"处理AI返回结果时出错: {str(e)}")
    else:
        messagebox.showerror("错误", "AI处理订单失败或返回的结果无效")
        logging.error("AI处理订单失败或返回的结果无效")

def save_to_db():
    global current_decoded_orders
    if not current_decoded_orders:
        messagebox.showwarning("警告", "没有可保存的数据")
        return
    
    result = save_to_database(current_decoded_orders)
    messagebox.showinfo("保存结果", result)

# 在GUI部分添加新的按钮
# 创建 Notebook (标签页容器)
notebook = ttk.Notebook(root)
notebook.grid(row=0, column=0, sticky="nsew")

# 创建第一个标签页 (订单处理)
order_processing_frame = ttk.Frame(notebook)

# 创建第二个标签页 (订单推荐)
order_recommendation_frame = ttk.Frame(notebook)

# 将两个页面添加到notebook
notebook.add(order_processing_frame, text="订单处理")
notebook.add(order_recommendation_frame, text="订单推荐")

process_decode_button = tk.Button(order_processing_frame, text="处理并解码", command=process_and_decode)
process_decode_button.grid(row=3, column=3, padx=10, pady=10, sticky="ew")
process_decode_button.bind("<Enter>", on_enter)
process_decode_button.bind("<Leave>", on_leave)

save_db_button = tk.Button(order_processing_frame, text="保存到数据库", command=save_to_db)
save_db_button.grid(row=4, column=1, padx=10, pady=10, sticky="ew")
save_db_button.bind("<Enter>", on_enter)
save_db_button.bind("<Leave>", on_leave)

# 添加一个全局变量来存储当前解码后的订单信息
current_decoded_orders = None



# 主程序部分保持不变
if __name__ == "__main__":
    logging.info("程序启动")
    init_db()

    # 创建 Notebook (标签页容器)
    notebook = ttk.Notebook(root)
    notebook.grid(row=0, column=0, sticky="nsew")

    # 创建第一个标签页 (订单处理)
    order_processing_frame = ttk.Frame(notebook)
    
    # 创建第二个标签页 (订单推荐)
    order_recommendation_frame = ttk.Frame(notebook)

    # 设置订单处理页面的布局
    order_processing_frame.grid_columnconfigure(0, weight=1)
    order_processing_frame.grid_columnconfigure(1, weight=1)
    order_processing_frame.grid_columnconfigure(2, weight=1)
    order_processing_frame.grid_columnconfigure(3, weight=1)
    order_processing_frame.grid_rowconfigure(1, weight=1)
    order_processing_frame.grid_rowconfigure(5, weight=1)

    # 创建标签和输入 (订单处理页面)
    tk.Label(order_processing_frame, text="订单信息:").grid(row=0, column=0, padx=10, pady=10, sticky="w")
    order_text = scrolledtext.ScrolledText(order_processing_frame, width=60, height=10)
    order_text.grid(row=1, column=0, columnspan=3, padx=10, pady=5, sticky="nsew")

    tk.Label(order_processing_frame, text="目标地址:").grid(row=2, column=0, padx=10, pady=10, sticky="w")
    address_entry = tk.Entry(order_processing_frame, width=50)
    address_entry.grid(row=2, column=1, columnspan=2, padx=10, pady=10, sticky="ew")

    # 创建按钮 (订单处理页面)
    calculate_button = tk.Button(order_processing_frame, text="计算", command=calculate_commute)
    calculate_button.grid(row=3, column=0, padx=10, pady=10, sticky="ew")
    calculate_button.bind("<Enter>", on_enter)
    calculate_button.bind("<Leave>", on_leave)

    copy_button = tk.Button(order_processing_frame, text="复制结果", command=copy_result)
    copy_button.grid(row=3, column=1, padx=10, pady=10, sticky="ew")
    copy_button.bind("<Enter>", on_enter)
    copy_button.bind("<Leave>", on_leave)

    reset_button = tk.Button(order_processing_frame, text="重置", command=reset_fields)
    reset_button.grid(row=3, column=2, padx=10, pady=10, sticky="ew")
    reset_button.bind("<Enter>", on_enter)
    reset_button.bind("<Leave>", on_leave)

    decode_button = tk.Button(order_processing_frame, text="地址解码", command=decode_addresses)
    decode_button.grid(row=3, column=3, padx=10, pady=10, sticky="ew")
    decode_button.bind("<Enter>", on_enter)
    decode_button.bind("<Leave>", on_leave)

    save_db_button = tk.Button(order_processing_frame, text="存入数据库", command=save_to_database)
    save_db_button.grid(row=4, column=0, padx=10, pady=10, sticky="ew")
    save_db_button.bind("<Enter>", on_enter)
    save_db_button.bind("<Leave>", on_leave)

    clean_db_button = tk.Button(order_processing_frame, text="清理重复数据", command=clean_duplicate_data)
    clean_db_button.grid(row=4, column=2, padx=10, pady=10, sticky="ew")
    clean_db_button.bind("<Enter>", on_enter)
    clean_db_button.bind("<Leave>", on_leave)

    clean_invalid_data_button = tk.Button(order_processing_frame, text="清理无效数据", command=clean_invalid_data)
    clean_invalid_data_button.grid(row=4, column=3, padx=10, pady=10, sticky="ew")
    clean_invalid_data_button.bind("<Enter>", on_enter)
    clean_invalid_data_button.bind("<Leave>", on_leave)

    # 创建输出框 (订单处理页面)
    tk.Label(order_processing_frame, text="输出结果:").grid(row=5, column=0, padx=10, pady=10, sticky="w")
    result_text = scrolledtext.ScrolledText(order_processing_frame, width=60, height=10)
    result_text.grid(row=6, column=0, columnspan=3, padx=10, pady=5, sticky="nsew")

    # 设置订单推荐页面的布局
    order_recommendation_frame.grid_columnconfigure(0, weight=1)
    order_recommendation_frame.grid_rowconfigure(2, weight=1)

    tk.Label(order_recommendation_frame, text="出发地址:").grid(row=0, column=0, padx=10, pady=10, sticky="w")
    recommendation_address_entry = tk.Entry(order_recommendation_frame, width=50)
    recommendation_address_entry.grid(row=0, column=1, padx=10, pady=10, sticky="ew")

    recommend_button = tk.Button(order_recommendation_frame, text="推荐订单", command=recommend_orders)
    recommend_button.grid(row=1, column=0, padx=10, pady=10, sticky="ew")
    recommend_button.bind("<Enter>", on_enter)
    recommend_button.bind("<Leave>", on_leave)

    copy_recommendation_button = tk.Button(order_recommendation_frame, text="复制结果", command=copy_recommendation_result)
    copy_recommendation_button.grid(row=1, column=1, padx=10, pady=10, sticky="ew")
    copy_recommendation_button.bind("<Enter>", on_enter)
    copy_recommendation_button.bind("<Leave>", on_leave)

    recommendation_result_text = scrolledtext.ScrolledText(order_recommendation_frame, width=60, height=20)
    recommendation_result_text.grid(row=2, column=0, columnspan=2, padx=10, pady=5, sticky="nsew")

    # 将两个页面添加到notebook
    notebook.add(order_processing_frame, text="订单处理")
    notebook.add(order_recommendation_frame, text="订单推荐")

    # 运行主窗口循环
    root.mainloop()
    logging.info("程序结束")