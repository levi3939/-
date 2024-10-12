from flask import Flask, render_template, request, jsonify
import mysql.connector
import requests
import re
import overpy
from openai import OpenAI
import json
import logging
from datetime import datetime
import os

app = Flask(__name__)
print("Current working directory:", os.getcwd())
# 创建logs文件夹(如果不存在)
if not os.path.exists('logs'):
    os.makedirs('logs')

# 配置日志
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler(f"logs/app_log_{datetime.now().strftime('%Y%m%d_%H%M%S')}.log", encoding='utf-8'),
        logging.StreamHandler()
    ]
)

# 数据库配置
DB_CONFIG = {
    'host': 'localhost',
    'user': 'root',
    'password': '232435',
    'database': 'address_cache'
}

# API 密钥
API_KEY = 'rPEhmHF9qxMJib2cmKD7rmvyTSVWA8DH'
DEEPSEEK_API_KEY = 'sk-b830f7dd0ad04f9990ace700d7cbeb7f'

# OpenAI 客户端
client = OpenAI(api_key=DEEPSEEK_API_KEY, base_url="https://api.deepseek.com")

# 其他全局变量和常量
SHANGHAI_DISTRICTS = [
    "黄浦", "徐汇", "长宁", "静安", "普陀", "虹口", "杨浦", "闵行", "宝山", "嘉定", 
    "浦东", "金山", "松江", "青浦", "奉贤", "崇明","黄浦区", "徐汇区", "长宁区", "静安区", 
    "普陀区", "虹口区", "杨浦区", "闵行区", "宝山区", "嘉定区", 
    "浦东新区", "金山区", "松江区", "青浦区", "奉贤区", "崇明区"
]

INVALID_INFO = [
    r"上海专职订单",
    r"有需要请加微信:xuecheng11003\(高提成诚招代理出单",
    r"今日新单加急出",
]

ORDER_FORMATS = {
    'format1': r'上海\d+',
    'format2': r'(?:' + '|'.join(SHANGHAI_DISTRICTS) + r').*',
    'format3': r'【.*】',
    'format4': r'SH\d+',
}

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

def extract_address(order: str):
    """提取地址"""
    full_address_pattern = r'(?:' + '|'.join(SHANGHAI_DISTRICTS) + r')[区]?.*?(?:路|街|巷|弄|号|楼|园|苑|城|湾|站|小区|大厦|公寓|村|花园|广场|学校|庭|隔壁)'
    full_match = re.search(full_address_pattern, order)
    if full_match:
        return full_match.group()

    district_pattern = r'(?:' + '|'.join(SHANGHAI_DISTRICTS) + r')[区]?.*?(?:\S+路|\S+街|\S+巷|\S+弄|\S+号|\S+楼|\S+园|\S+苑|\S+城|\S+湾|\S+站|\S+小区|\S+大厦|\S+公寓|\S+村|\S+花园|\S+广场|\S+学校)'
    district_match = re.search(district_pattern, order)
    if district_match:
        return district_match.group()

    road_pattern = r'[\u4e00-\u9fa5]{2,}(?:路|街|巷|弄)(?:\d+号?)?'
    road_match = re.search(road_pattern, order)
    if road_match:
        return road_match.group()

    return None

def get_geocode(address: str):
    logging.info(f"获取地理编码: {address}")
    try:
        connection = mysql.connector.connect(**DB_CONFIG)
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
            'city': '上海市'
        }
        response = requests.get(url, params=params, timeout=10)
        data = response.json()
        if data['status'] == 0 and 'result' in data and 'location' in data['result']:
            lat = data['result']['location']['lat']
            lng = data['result']['location']['lng']
            
            if 30.7 <= lat <= 31.5 and 120.9 <= lng <= 122.1:
                uid = data['result'].get('uid', '')
                
                cursor.execute("INSERT INTO addresses (address, latitude, longitude, uid) VALUES (%s, %s, %s, %s)",
                                 (address, lat, lng, uid))
                connection.commit()
                return lat, lng, uid
            else:
                return None
        
        return None
    except mysql.connector.Error as e:
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
        'origin': f"{lat_lng_origin[0]},{lat_lng_origin[1]}",
        'destination': f"{lat_lng_destination[0]},{lat_lng_destination[1]}",
        'ak': API_KEY,
        'coord_type': 'bd09ll',
        'ret_coordtype': 'bd09ll',
    }
    
    if origin_uid:
        params['origin_uid'] = origin_uid
    
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
            logging.error(f"获取公交路线时出错 (尝试 {attempt+1}/{max_retries}): {str(e)}")
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
                        formatted_route.append(f"步行{sub_step.get('distance', 0) / 1000:.1f}公里")
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
            max_tokens=10000
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

def save_to_database(decoded_orders):
    connection = None
    try:
        connection = mysql.connector.connect(**DB_CONFIG)
        cursor = connection.cursor()

        for order in decoded_orders:
            cursor.execute("""
            INSERT INTO orders (order_id, origin, full_text)
            VALUES (%s, %s, %s)
            """, (order['order_id'], order['address'], order['full_text']))

            if 'latitude' in order and 'longitude' in order:
                cursor.execute("""
                INSERT IGNORE INTO addresses (address, latitude, longitude, uid)
                VALUES (%s, %s, %s, %s)
                """, (order['address'], order['latitude'], order['longitude'], order.get('uid', '')))

        connection.commit()
        return "数据已成功保存到数据库"

    except mysql.connector.Error as e:
        if connection:
            connection.rollback()
        return f"保存到数据库时出���: {str(e)}"

    finally:
        if connection and connection.is_connected():
            cursor.close()
            connection.close()

def clean_duplicate_data():
    try:
        connection = mysql.connector.connect(**DB_CONFIG)
        cursor = connection.cursor()

        cursor.execute("SELECT COUNT(*) FROM orders")
        orders_before = cursor.fetchone()[0]
        cursor.execute("SELECT COUNT(*) FROM addresses")
        addresses_before = cursor.fetchone()[0]

        cursor.execute('''
            DELETE o1 FROM orders o1
            INNER JOIN orders o2 
            WHERE o1.origin = o2.origin 
            AND o1.id < o2.id
        ''')
        deleted_orders = cursor.rowcount

        cursor.execute('''
            DELETE a1 FROM addresses a1
            INNER JOIN addresses a2 
            WHERE a1.latitude = a2.latitude 
            AND a1.longitude = a2.longitude
            AND a1.id < a2.id
        ''')
        deleted_addresses = cursor.rowcount

        connection.commit()
        total_deleted = deleted_orders + deleted_addresses

        cursor.execute("SELECT COUNT(*) FROM orders")
        orders_after = cursor.fetchone()[0]
        cursor.execute("SELECT COUNT(*) FROM addresses")
        addresses_after = cursor.fetchone()[0]

        return f"清理前：订单数 {orders_before}，地址数 {addresses_before}\n" \
               f"清理后：订单数 {orders_after}，地址数 {addresses_after}\n" \
               f"共清理 {total_deleted} 条重复数据"

    except mysql.connector.Error as e:
        return f"清理重复数据时出错: {str(e)}"
    finally:
        if connection and connection.is_connected():
            cursor.close()
            connection.close()

def clean_invalid_data():
    try:
        connection = mysql.connector.connect(**DB_CONFIG)
        cursor = connection.cursor()

        cursor.execute("""
            DELETE FROM addresses 
            WHERE latitude < 30.7 OR latitude > 31.5 
            OR longitude < 120.9 OR longitude > 122.1
        """)

        connection.commit()
        deleted_count = cursor.rowcount
        return f"已清理 {deleted_count} 条无效数据"

    except mysql.connector.Error as e:
        return f"清理无效数据时出错: {str(e)}"
    finally:
        if connection and connection.is_connected():
            cursor.close()
            connection.close()

def recommend_orders(start_address):
    try:
        connection = mysql.connector.connect(**DB_CONFIG)
        cursor = connection.cursor()

        cursor.execute("SELECT order_id, origin, full_text FROM orders")
        all_orders = cursor.fetchall()

        if not all_orders:
            return "数据库中没有订单数据"

        recommended_orders = []
        for order in all_orders:
            order_id, destination, full_text = order
            route = get_best_route_time(start_address, destination)
            if route and route != "无法获取通勤路线" and route != "无法获取地理编码":
                time_match = re.search(r'总时间: (\d+)小时(\d+)分钟|总时间: (\d+)分钟', route)
                if time_match:
                    hours = int(time_match.group(1) or 0)
                    minutes = int(time_match.group(2) or time_match.group(3) or 0)
                    total_minutes = hours * 60 + minutes
                    if total_minutes <= 90:
                        recommended_orders.append((total_minutes, order_id, destination, route, full_text))

        recommended_orders.sort(key=lambda x: x[0])

        if recommended_orders:
            result = "\n\n".join([f"订单号: {order_id}\n目的地: {destination}\n通勤路线: {route}\n原始订单: {full_text}" 
                                  for _, order_id, destination, route, full_text in recommended_orders])
        else:
            result = "没有找到符合条件的订单"

        return result

    except mysql.connector.Error as e:
        return f"推荐订单时出错: {str(e)}"
    finally:
        if connection and connection.is_connected():
            cursor.close()
            connection.close()

@app.route('/')
def index():
    return render_template('index.html')

@app.route('/process_order', methods=['POST'])
def process_order():
    order_input = request.form['order_input']
    user_address = request.form['user_address']
    
    try:
        parsed_orders = process_orders_with_ai(order_input)
        if parsed_orders:
            decoded_orders = decode_addresses(parsed_orders)
            result = []
            for order in decoded_orders:
                route = get_best_route_time(user_address, order['address'])
                result.append({
                    'order_id': order['order_id'],
                    'destination': order['address'],
                    'route': route,
                    'full_text': order['full_text']
                })
            return jsonify({'success': True, 'result': result})
        else:
            return jsonify({'success': False, 'error': 'AI处理订单失败'})
    except Exception as e:
        logging.error(f"处理订单时出错: {str(e)}")
        return jsonify({'success': False, 'error': str(e)})

@app.route('/save_to_db', methods=['POST'])
def save_to_db():
    decoded_orders = request.json['decoded_orders']
    result = save_to_database(decoded_orders)
    return jsonify({'message': result})

@app.route('/clean_duplicate_data', methods=['POST'])
def clean_duplicate():
    result = clean_duplicate_data()
    return jsonify({'message': result})

@app.route('/clean_invalid_data', methods=['POST'])
def clean_invalid():
    result = clean_invalid_data()
    return jsonify({'message': result})

@app.route('/recommend_orders', methods=['POST'])
def recommend():
    start_address = request.form['start_address']
    result = recommend_orders(start_address)
    return jsonify({'result': result})

@app.route('/calculate_route', methods=['POST'])
def calculate_route():
    order_input = request.form['order_input']
    user_address = request.form['user_address']
    
    try:
        parsed_orders = process_orders_with_ai(order_input)
        if parsed_orders:
            result = []
            for order in parsed_orders:
                route = get_best_route_time(user_address, order['address'])
                result.append({
                    'order_id': order['order_id'],
                    'destination': order['address'],
                    'route': route
                })
            return jsonify({'success': True, 'result': result})
        else:
            return jsonify({'success': False, 'error': 'AI处理订单失败'})
    except Exception as e:
        logging.error(f"计算路线时出错: {str(e)}")
        return jsonify({'success': False, 'error': str(e)})

csp = (
    "script-src 'self' https://alidcdn.com https://another-cdn.com 'wasm-unsafe-eval' 'inline-speculation-rules';"
    "style-src 'self' https://fonts.googleapis.com;"
    "font-src 'self' https://fonts.gstatic.com;"
)

@app.after_request
def add_security_headers(response):
    response.headers['Content-Security-Policy'] = csp
    return response

if __name__ == '__main__':
    app.run(debug=True, port=8080) # 或者任何其他可用的端口号