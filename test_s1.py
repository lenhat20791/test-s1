from binance.client import Client
from datetime import datetime
import re
import os
import traceback 
import sys
import pandas as pd
import pytz
from pathlib import Path
from s1 import pivot_data, detect_pivot, save_log, set_current_time_and_user

# Chuyển đổi UTC sang múi giờ Việt Nam
utc_time = "2025-03-19 08:01:00"   # UTC time
utc = pytz.UTC
vietnam_tz = pytz.timezone('Asia/Ho_Chi_Minh')

# Parse UTC time và chuyển sang múi giờ Việt Nam
utc_dt = datetime.strptime(utc_time, '%Y-%m-%d %H:%M:%S').replace(tzinfo=utc)
vietnam_time = utc_dt.astimezone(vietnam_tz)
current_time = vietnam_time.strftime('%Y-%m-%d %H:%M:%S')

current_user = "lenhat20791"
DEBUG_LOG_FILE = "debug_historical_test.log"

print(f"Current Date and Time (UTC): {utc_time}")
print(f"Current User's Login: {current_user}")
set_current_time_and_user(current_time, current_user)

class S1HistoricalTester:
    def __init__(self, user_login="lenhat20791"):
        try:
            self.client = Client()
            self.debug_log_file = DEBUG_LOG_FILE
            self.user_login = user_login
            self.symbol = "BTCUSDT"           # Thêm symbol
            self.interval = "30m"             # Thêm interval
            self.clear_log_file()
            
            # Test kết nối
            self.client.ping()
            self.log_message("✅ Kết nối Binance thành công", "SUCCESS")
        except Exception as e:
            self.log_message(f"❌ Lỗi kết nối Binance: {str(e)}", "ERROR")
            raise
        
    def clear_log_file(self):
        """Xóa nội dung của file log để bắt đầu test mới"""
        try:
            with open(self.debug_log_file, 'w', encoding='utf-8') as f:
                f.write('=== Log Initialized ===\n')
        except Exception as e:
            print(f"Error clearing log file: {str(e)}")

    def log_message(self, message, level="INFO"):
        """Ghi log ra console và file với level"""
        timestamp = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
        formatted_message = f"[{timestamp}] [{level}] {message}"
        print(formatted_message)
        with open(self.debug_log_file, "a", encoding="utf-8") as f:
            f.write(f"{formatted_message}\n")

    def get_pivot_status(self):
        """Lấy thông tin về trạng thái pivot hiện tại"""
        status_info = []
        
        # Lấy các pivot gần nhất
        recent_pivots = pivot_data.get_recent_pivots(4)
        
        if recent_pivots:
            status_info.append("\nPivot gần nhất:")
            for pivot in recent_pivots:
                status_info.append(f"- {pivot['type']} tại ${pivot['price']:,.2f} ({pivot['time']})")
        
        return status_info

    def analyze_price_action(self, current_price, last_pivot):
        """Phân tích price action"""
        if not last_pivot:
            return "Chưa có pivot để xác định xu hướng"
            
        price_diff = current_price - last_pivot['price']
        trend = "Uptrend" if price_diff > 0 else "Downtrend" if price_diff < 0 else "Sideway"
        return f"Xu hướng: {trend} (${abs(price_diff):,.2f} từ pivot cuối)"

    def save_test_results(self, df, results):
        try:
            # Tạo DataFrame mới chỉ cho các pivot
            pivot_data = []
            for pivot in results:
                # Tìm datetime tương ứng từ DataFrame gốc
                pivot_datetime = df[df['time'] == pivot['time']]['datetime'].iloc[0]
                
                pivot_data.append({
                    'datetime': pivot_datetime,
                    'price': pivot['price'],
                    'pivot_type': pivot['type']
                })
            
            # Chuyển list thành DataFrame
            pivot_df = pd.DataFrame(pivot_data)
            
            # Sắp xếp theo thời gian
            pivot_df = pivot_df.sort_values('datetime')
            
            with pd.ExcelWriter('test_results.xlsx', engine='xlsxwriter') as writer:
                # Ghi vào sheet Pivot Analysis
                pivot_df.to_excel(writer, sheet_name='Pivot Analysis', index=False)
                
                workbook = writer.book
                worksheet = writer.sheets['Pivot Analysis']
                
                # Định dạng cột
                date_format = workbook.add_format({'num_format': 'yyyy-mm-dd hh:mm:ss'})
                price_format = workbook.add_format({'num_format': '$#,##0.00'})
                
                worksheet.set_column('A:A', 20, date_format)  # datetime
                worksheet.set_column('B:B', 15, price_format) # price
                worksheet.set_column('C:C', 12)              # pivot_type
                
                # Thêm thống kê
                stats_row = len(pivot_df) + 3
                stats_format = workbook.add_format({'bold': True})
                
                worksheet.write(stats_row, 0, "Thống kê:", stats_format)
                worksheet.write(stats_row + 1, 0, "Tổng số pivot:")
                worksheet.write(stats_row + 1, 1, len(pivot_df))
                
                # Thống kê theo loại pivot
                pivot_counts = pivot_df['pivot_type'].value_counts()
                worksheet.write(stats_row + 2, 0, "Phân bố pivot:", stats_format)
                
                row = stats_row + 3
                for pivot_type in ['HH', 'HL', 'LH', 'LL']:
                    if pivot_type in pivot_counts:
                        worksheet.write(row, 0, f"{pivot_type}:")
                        worksheet.write(row, 1, pivot_counts[pivot_type])
                        row += 1
                
                # Thêm biểu đồ
                chart = workbook.add_chart({'type': 'scatter'})
                
                # Thêm series cho price
                chart.add_series({
                    'name': 'Price',
                    'categories': f'=Pivot Analysis!$A$2:$A${len(pivot_df) + 1}',
                    'values': f'=Pivot Analysis!$B$2:$B${len(pivot_df) + 1}',
                    'line': {'width': 2.25},
                    'marker': {'type': 'circle', 'size': 8}
                })
                
                chart.set_title({'name': 'Pivot Points Analysis'})
                chart.set_x_axis({
                    'name': 'Time',
                    'num_format': 'dd/mm/yyyy\nhh:mm',
                    'label_position': 'low',
                    'major_unit': 1,
                    'major_unit_type': 'days'
                })
                chart.set_y_axis({
                    'name': 'Price',
                    'num_format': '$#,##0'
                })
                
                chart.set_size({'width': 920, 'height': 600})
                worksheet.insert_chart('E2', chart)
                
            self.log_message("\nĐã lưu kết quả test vào file test_results.xlsx", "SUCCESS")
            self.log_message(f"Tổng số pivot: {len(pivot_df)}", "INFO")
            self.log_message("Phân bố pivot:", "INFO")
            for pivot_type in ['HH', 'HL', 'LH', 'LL']:
                if pivot_type in pivot_counts:
                    self.log_message(f"- {pivot_type}: {pivot_counts[pivot_type]}", "INFO")
            
            return True
            
        except Exception as e:
            self.log_message(f"Lỗi khi lưu Excel: {str(e)}", "ERROR")
            self.log_message(traceback.format_exc(), "ERROR")
            return False

    def run_test(self):
        """Chạy historical test cho S1"""
        try:
            # Set thời gian test với UTC
            start_time = datetime(2025, 3, 15, 0, 0, 0)  # 00:00 15/03/2025 UTC
            end_time = datetime(2025, 3, 20, 1, 50, 12)    # 01:50:12 20/03/2025 UTC
            
            self.log_message("\n=== Bắt đầu test S1 ===", "INFO")
            self.log_message(f"Symbol: {self.symbol}")
            self.log_message(f"Interval: {self.interval}")
            self.log_message(f"User: {self.user_login}")
            self.log_message(f"Thời gian bắt đầu (UTC): {start_time.strftime('%Y-%m-%d %H:%M:%S')}")
            self.log_message(f"Thời gian kết thúc (UTC): {end_time.strftime('%Y-%m-%d %H:%M:%S')}")
                
            # Lấy dữ liệu từ Binance
            klines = self.client.get_historical_klines(
                self.symbol,
                Client.KLINE_INTERVAL_30MINUTE,
                start_str=int(start_time.timestamp() * 1000),
                end_str=int(end_time.timestamp() * 1000)
            )
            
            if not klines:
                self.log_message("Không tìm thấy dữ liệu cho khoảng thời gian này", "ERROR")
                return
            
            # Chuyển đổi dữ liệu
            df = pd.DataFrame(klines, columns=[
                'timestamp', 'open', 'high', 'low', 'close', 
                'volume', 'close_time', 'quote_volume', 'trades',
                'buy_base_volume', 'buy_quote_volume', 'ignore'
            ])

            # Chuyển đổi timestamp sang datetime với múi giờ UTC
            df['datetime'] = pd.to_datetime(df['timestamp'], unit='ms', utc=True)

            # Chuyển đổi sang múi giờ Việt Nam
            vietnam_tz = pytz.timezone('Asia/Ho_Chi_Minh')
            df['datetime'] = df['datetime'].dt.tz_convert(vietnam_tz)

            # Loại bỏ thông tin timezone để có thể lưu vào Excel
            df['datetime'] = df['datetime'].dt.tz_localize(None)

            # Format lại cột time chỉ lấy giờ:phút
            df['time'] = df['datetime'].dt.strftime('%H:%M')

            # Chọn và đổi tên các cột cần thiết
            df = df[['datetime', 'time', 'high', 'low', 'close']]
            df = df.rename(columns={'close': 'price'})

            # Chuyển đổi các cột giá sang float
            for col in ['high', 'low', 'price']:
                df[col] = df[col].astype(float)
            
            self.log_message(f"\nTổng số nến: {len(df)}", "INFO")
            
            # Reset trạng thái và thêm pivots đã biết
            pivot_data.clear_all()
            
            # Thêm 2 pivot ban đầu
            initial_pivots = [
                {
                    'type': 'HL',
                    'price': 81739.0,
                    'time': '13:30',
                    'direction': 'low',
                    'datetime': datetime(2025, 3, 14, 13, 30)
                },
                {
                    'type': 'HH',
                    'price': 85274.0,
                    'time': '22:30',
                    'direction': 'high',
                    'datetime': datetime(2025, 3, 14, 22, 30)
                }
            ]
            
            # Thêm pivot ban đầu vào confirmed_pivots
            for pivot in initial_pivots:
                pivot_data.confirmed_pivots.append(pivot)
                
            self.log_message("\nĐã thêm pivot ban đầu:", "INFO")
            for pivot in initial_pivots:
                self.log_message(f"- {pivot['type']} tại ${pivot['price']:,.2f} ({pivot['time']})", "INFO")

            # Chạy test
            self.log_message("\nBắt đầu phát hiện pivot...", "INFO")
            results = initial_pivots.copy()  # Bắt đầu với các pivot ban đầu
            last_pivot_index = -1  # Lưu index của pivot cuối cùng

            for index, row in df.iterrows():
                # Log chi tiết cho mỗi nến
                self.log_message(f"\n=== Phân tích nến {row['time']} ===", "INFO")
                self.log_message(f"Giá: ${row['price']:,.2f}")
                self.log_message(f"High: ${row['high']:,.2f}")
                self.log_message(f"Low: ${row['low']:,.2f}")

                price_data = {
                    'time': row['time'],
                    'price': row['price'],
                    'high': row['high'],
                    'low': row['low']
                }

                # Thêm dữ liệu giá và xử lý
                pivot_data.add_price_data(price_data)
                
                # Kiểm tra khoảng cách với pivot cuối
                if last_pivot_index != -1 and (index - last_pivot_index) < 5:
                    continue  # Bỏ qua nếu chưa đủ 5 nến từ pivot cuối

                # Kiểm tra pivot
                current_pivot = None
                if row['high'] > row['low']:  
                    # Kiểm tra high trước low
                    high_pivot = pivot_data.detect_pivot(row['high'], 'high')
                    if high_pivot and high_pivot['type'] in ['HH', 'HL', 'LH', 'LL']:
                        current_pivot = high_pivot
                        last_pivot_index = index
                        self.log_message(f"✅ Phát hiện pivot {high_pivot['type']} tại high (${row['high']:,.2f})", "SUCCESS")
                    
                    low_pivot = pivot_data.detect_pivot(row['low'], 'low')
                    if low_pivot and low_pivot['type'] in ['HH', 'HL', 'LH', 'LL']:
                        current_pivot = low_pivot
                        last_pivot_index = index
                        self.log_message(f"✅ Phát hiện pivot {low_pivot['type']} tại low (${row['low']:,.2f})", "SUCCESS")
                else:  
                    # Kiểm tra low trước high
                    low_pivot = pivot_data.detect_pivot(row['low'], 'low')
                    if low_pivot and low_pivot['type'] in ['HH', 'HL', 'LH', 'LL']:
                        current_pivot = low_pivot
                        last_pivot_index = index
                        self.log_message(f"✅ Phát hiện pivot {low_pivot['type']} tại low (${row['low']:,.2f})", "SUCCESS")
                    
                    high_pivot = pivot_data.detect_pivot(row['high'], 'high')
                    if high_pivot and high_pivot['type'] in ['HH', 'HL', 'LH', 'LL']:
                        current_pivot = high_pivot
                        last_pivot_index = index
                        self.log_message(f"✅ Phát hiện pivot {high_pivot['type']} tại high (${row['high']:,.2f})", "SUCCESS")

                # Chỉ thêm vào results nếu là pivot hợp lệ và chưa tồn tại
                if current_pivot and current_pivot not in results:
                    results.append(current_pivot)
                    
                    # Log trạng thái pivot
                    status_info = self.get_pivot_status()
                    for info in status_info:
                        self.log_message(info, "STATUS")
                    
                    # Log xu hướng
                    trend_info = self.analyze_price_action(row['price'], current_pivot)
                    self.log_message(trend_info, "TREND")
            
            # Lấy danh sách pivot cuối cùng từ pivot_data
            final_pivots = pivot_data.confirmed_pivots.copy()  # Lấy trực tiếp từ pivot_data thay vì dùng results
            
            # Tổng kết kết quả
            self.log_message("\n=== Tổng kết kết quả ===", "SUMMARY")
            self.log_message(f"Tổng số nến: {len(df)}")
            self.log_message(f"Tổng số pivot đã xác nhận: {len(final_pivots)}")
            
            if final_pivots:
                self.log_message("\nDanh sách pivot đã xác nhận:")
                for pivot in final_pivots:
                    self.log_message(f"- {pivot['type']} tại ${pivot['price']:,.2f} ({pivot['time']})")
            
            # Lưu kết quả vào Excel với danh sách pivot cuối cùng
            self.save_test_results(df, final_pivots)
            
            return final_pivots
            
# Entry point
# Thay thế phần cuối của file test_s1.py

def main():
    try:
        # Chuyển đổi UTC sang múi giờ Việt Nam
        utc_time = "2025-03-20 06:34:03"   # UTC time
        utc = pytz.UTC
        vietnam_tz = pytz.timezone('Asia/Ho_Chi_Minh')

        # Parse UTC time và chuyển sang múi giờ Việt Nam
        utc_dt = datetime.strptime(utc_time, '%Y-%m-%d %H:%M:%S').replace(tzinfo=utc)
        vietnam_time = utc_dt.astimezone(vietnam_tz)
        current_time = vietnam_time.strftime('%Y-%m-%d %H:%M:%S')

        current_user = "lenhat20791"
        
        print(f"Current Date and Time (UTC): {utc_time}")
        print(f"Current User's Login: {current_user}")
        
        # Set thời gian và user hiện tại
        set_current_time_and_user(current_time, current_user)
        
        # Khởi tạo và chạy tester
        tester = S1HistoricalTester()
        print("Đang chạy historical test cho S1...")
        results = tester.run_test()
        
        print("\nTest hoàn tất! Kiểm tra file debug_historical_test.log và test_results.xlsx để xem chi tiết.")
        return results
        
    except Exception as e:
        print(f"Lỗi: {str(e)}")
        print(traceback.format_exc())
        return None

if __name__ == "__main__":
    main()
