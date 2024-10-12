from setuptools import setup

APP = ['version1.py']
DATA_FILES = []
OPTIONS = {
    'argv_emulation': True,
    'packages': ['tkinter', 'requests', 'mysql.connector', 'overpy', 'openai'],
    'iconfile': 'path/to/your/icon.icns',  # 如果您有应用图标的话
    'plist': {
        'CFBundleName': "订单处理系统",
        'CFBundleShortVersionString': "1.0.0",
        'CFBundleVersion': "1.0.0",
        'CFBundleIdentifier': "com.yourcompany.ordersystem",
        'NSHumanReadableCopyright': "Copyright © 2024 Your Company Name, All Rights Reserved",
        'NSHighResolutionCapable': True,
    }
}

setup(
    app=APP,
    data_files=DATA_FILES,
    options={'py2app': OPTIONS},
    setup_requires=['py2app'],
)