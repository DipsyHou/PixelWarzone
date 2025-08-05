#!/usr/bin/env python3
import requests
import json
import sys
import time
from datetime import datetime

class DatabaseCleaner:
    def __init__(self, server_url="http://localhost:3000", admin_password="admin123"):
        self.server_url = server_url
        self.admin_password = admin_password
    
    def check_server_status(self):
        """检查服务器状态"""
        try:
            response = requests.get(f"{self.server_url}/", timeout=5)
            return response.status_code == 200
        except:
            return False
    
    def get_database_stats(self):
        """获取数据库统计信息"""
        try:
            response = requests.post(
                f"{self.server_url}/api/admin/stats",
                json={"admin_password": self.admin_password},  # 使用JSON格式
                headers={'Content-Type': 'application/json'},
                timeout=5
            )
            if response.status_code == 200:
                return response.json()
            elif response.status_code == 403:
                print("❌ 管理员密码错误")
                return None
            else:
                print(f"❌ 获取统计失败: {response.status_code}")
                print(f"响应: {response.text}")
                return None
        except Exception as e:
            print(f"❌ 网络错误: {e}")
            return None
    
    def clear_database(self):
        """清空数据库"""
        try:
            response = requests.post(
                f"{self.server_url}/api/admin/clear-database",
                json={"admin_password": self.admin_password},  # 使用JSON格式
                headers={'Content-Type': 'application/json'},
                timeout=10
            )
            
            if response.status_code == 200:
                result = response.json()
                return result.get("success", False), result
            elif response.status_code == 403:
                return False, {"error": "管理员密码错误"}
            elif response.status_code == 422:
                return False, {"error": "请求格式错误，请检查管理员密码"}
            else:
                return False, {"error": f"HTTP错误: {response.status_code}", "details": response.text}
                
        except Exception as e:
            return False, {"error": f"网络错误: {str(e)}"}
    
    def display_stats(self, stats):
        """显示统计信息"""
        if not stats:
            return
            
        print(f"📊 数据库状态:")
        print(f"  用户数量: {stats.get('users_count', 0)}")
        print(f"  活跃会话: {stats.get('active_sessions', 0)}")
        print(f"  活跃房间: {stats.get('active_rooms', 0)}")
        print(f"  房间中用户: {stats.get('users_in_rooms', 0)}")
        print(f"  在线玩家: {stats.get('total_players_online', 0)}")
        
        if stats.get('room_details'):
            print(f"\n🏠 房间详情:")
            for room in stats['room_details']:
                print(f"  - {room['name']} (ID: {room['id']}) - {room['players']}人 - 创建者: {room['creator']}")
    
    def run_interactive(self):
        """交互式清理"""
        print("🔧 数据库清理工具")
        print("=" * 60)
        print(f"时间: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
        print(f"服务器: {self.server_url}")
        print("=" * 60)
        
        # 检查服务器状态
        print("🔍 检查服务器状态...", end=" ")
        if not self.check_server_status():
            print("❌")
            print("错误: 无法连接到服务器")
            print("请确保后端服务器正在运行")
            return False
        print("✅")
        
        # 获取当前统计
        print("📊 获取数据库状态...", end=" ")
        stats = self.get_database_stats()
        if stats is None:
            print("❌")
            return False
        print("✅")
        
        print()
        self.display_stats(stats)
        
        # 检查是否有数据需要清理
        total_data = (
            stats.get('users_count', 0) + 
            stats.get('active_sessions', 0) + 
            stats.get('active_rooms', 0)
        )
        
        if total_data == 0:
            print("\n✨ 数据库已经是空的，无需清理")
            return True
        
        # 警告信息
        print(f"\n⚠️  警告: 此操作将永久删除所有数据!")
        print("包括:")
        print("  - 所有用户账户和统计数据")
        print("  - 所有登录会话")
        print("  - 所有游戏房间")
        print("  - 所有在线连接")
        
        # 确认操作
        if "--force" in sys.argv:
            confirm = "YES"
            print("🚀 强制模式: 跳过确认")
        else:
            print()
            confirm = input("确定要清空数据库吗? (输入 'YES' 确认, 其他任意键取消): ")
        
        if confirm != "YES":
            print("❌ 操作已取消")
            return False
        
        # 执行清理
        print("\n🔧 正在清空数据库...")
        success, result = self.clear_database()
        
        if success:
            print("✅ 数据库清空成功!")
            if result.get("cleared"):
                cleared = result["cleared"]
                print(f"📝 清理统计:")
                print(f"  - 用户: {cleared.get('users', 0)}")
                print(f"  - 会话: {cleared.get('sessions', 0)}")
                print(f"  - 房间: {cleared.get('rooms', 0)}")
                print(f"  - 在线玩家: {cleared.get('total_players', 0)}")
            
            # 验证清理结果
            print("\n🔍 验证清理结果...")
            time.sleep(1)
            new_stats = self.get_database_stats()
            if new_stats:
                total_remaining = (
                    new_stats.get('users_count', 0) + 
                    new_stats.get('active_sessions', 0) + 
                    new_stats.get('active_rooms', 0)
                )
                if total_remaining == 0:
                    print("🎉 验证成功: 数据库已完全清空")
                else:
                    print("⚠️  注意: 仍有部分数据存在")
                    self.display_stats(new_stats)
            
            return True
        else:
            print(f"❌ 清空失败: {result.get('error', '未知错误')}")
            if result.get('details'):
                print(f"详细信息: {result['details']}")
            return False

def main():
    """主函数"""
    # 检查依赖
    try:
        import requests
    except ImportError:
        print("❌ 错误: 未安装 requests 库")
        print("请运行: pip install requests")
        return
    
    # 解析命令行参数
    server_url = "http://localhost:3000"
    admin_password = "admin123"  # 更改为你的管理员密码
    
    cleaner = DatabaseCleaner(server_url, admin_password)
    cleaner.run_interactive()

if __name__ == "__main__":
    main()