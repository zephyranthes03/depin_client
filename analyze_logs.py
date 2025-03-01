import sqlite3
from collections import Counter

LOG_DB = "./streaming_logs.db"

def calculate_node_rewards():
    """노드별 기여도 측정 및 보상 계산"""
    conn = sqlite3.connect(LOG_DB)
    cursor = conn.cursor()
    
    # 노드별 다운로드 횟수 계산
    cursor.execute("SELECT client_ip, COUNT(*) FROM streaming_logs GROUP BY client_ip")
    results = cursor.fetchall()
    conn.close()
    
    rewards = {ip: count * 0.01 for ip, count in results}  # 예: 1회당 0.01 토큰 보상
    return rewards

if __name__ == "__main__":
    print("📊 노드별 기여도 측정 결과:", calculate_node_rewards())
