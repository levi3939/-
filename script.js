function showLoading() {
    document.getElementById('loading').style.display = 'block';
    document.getElementById('result').innerHTML = '';
}

function hideLoading() {
    document.getElementById('loading').style.display = 'none';
}

function processOrder() {
    showLoading();
    const orderInput = document.getElementById('order-input').value;
    const userAddress = document.getElementById('user-address').value;

    fetch('/process_order', {
        method: 'POST',
        headers: {
            'Content-Type': 'application/x-www-form-urlencoded',
        },
        body: `order_input=${encodeURIComponent(orderInput)}&user_address=${encodeURIComponent(userAddress)}`
    })
    .then(response => response.json())
    .then(data => {
        hideLoading();
        if (data.success) {
            let resultHtml = '';
            data.result.forEach(order => {
                resultHtml += `
                    <p>订单号: ${order.order_id}</p>
                    <p>目的地: ${order.destination}</p>
                    <p>通勤路线: ${order.route}</p>
                    <p>原始订单: ${order.full_text}</p>
                    <hr>
                `;
            });
            document.getElementById('result').innerHTML = resultHtml;
        } else {
            document.getElementById('result').innerHTML = `错误: ${data.error}`;
        }
    })
    .catch(error => {
        hideLoading();
        console.error('Error:', error);
        document.getElementById('result').innerHTML = '处理订单时出错';
    });
}

function calculateRoute() {
    showLoading();
    const orderInput = document.getElementById('order-input').value;
    const userAddress = document.getElementById('user-address').value;

    fetch('/calculate_route', {
        method: 'POST',
        headers: {
            'Content-Type': 'application/x-www-form-urlencoded',
        },
        body: `order_input=${encodeURIComponent(orderInput)}&user_address=${encodeURIComponent(userAddress)}`
    })
    .then(response => response.json())
    .then(data => {
        hideLoading();
        if (data.success) {
            let resultHtml = '';
            data.result.forEach(order => {
                resultHtml += `
                    <p>订单号: ${order.order_id}</p>
                    <p>目的地: ${order.destination}</p>
                    <p>通勤路线: ${order.route}</p>
                    <hr>
                `;
            });
            document.getElementById('result').innerHTML = resultHtml;
        } else {
            document.getElementById('result').innerHTML = `错误: ${data.error}`;
        }
    })
    .catch(error => {
        hideLoading();
        console.error('Error:', error);
        document.getElementById('result').innerHTML = '计算路线时出错';
    });
}

function saveToDb() {
    // 实现保存到数据库的逻辑
}

function cleanDuplicateData() {
    fetch('/clean_duplicate_data', { method: 'POST' })
    .then(response => response.json())
    .then(data => {
        alert(data.message);
    })
    .catch(error => {
        console.error('Error:', error);
        alert('清理重复数据时出错');
    });
}

function cleanInvalidData() {
    fetch('/clean_invalid_data', { method: 'POST' })
    .then(response => response.json())
    .then(data => {
        alert(data.message);
    })
    .catch(error => {
        console.error('Error:', error);
        alert('清理无效数据时出错');
    });
}

function recommendOrders() {
    showLoading();
    const startAddress = document.getElementById('start-address').value;

    fetch('/recommend_orders', {
        method: 'POST',
        headers: {
            'Content-Type': 'application/x-www-form-urlencoded',
        },
        body: `start_address=${encodeURIComponent(startAddress)}`
    })
    .then(response => response.json())
    .then(data => {
        hideLoading();
        document.getElementById('recommendation-result').innerHTML = data.result;
    })
    .catch(error => {
        hideLoading();
        console.error('Error:', error);
        document.getElementById('recommendation-result').innerHTML = '推荐订单时出错';
    });
}

// 在文件末尾添加以下函数

function copyResult() {
    const resultElement = document.getElementById('result');
    const resultText = resultElement.innerText;

    if (resultText) {
        navigator.clipboard.writeText(resultText).then(function() {
            alert('结果已复制到剪贴板');
        }, function(err) {
            console.error('无法复制文本: ', err);
            alert('复制失败，请手动复制');
        });
    } else {
        alert('没有可复制的结果');
    }
}
