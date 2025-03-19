from binance.client import Client
from datetime import datetime
import re
import os
import sys
import pandas as pd
import pytz
from pathlib import Path
from s1 import pivot_data, detect_pivot, save_log, set_current_time_and_user

# Chuyển đổi UTC sang múi giờ Việt Nam
utc_time = "2025-03-19 03:03:04"  # UTC time
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
        self.client = Client()
        self.debug_log_file = DEBUG_LOG_FILE
        self.user_login = user_login
        self.clear_log_file()
        
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
        
        # Lấy thông tin high/low gần nhất
        last_high = pivot_data.get_last_high() if hasattr(pivot_data, 'get_last_high') else None
        last_low = pivot_data.get_last_low() if hasattr(pivot_data, 'get_last_low') else None
        
        if last_high:
            status_info.append(f"Last High: ${last_high['price']:,.2f} tại {last_high['time']}")
        if last_low:
            status_info.append(f"Last Low: ${last_low['price']:,.2f} tại {last_low['time']}")
        
        # Lấy thông tin pivot tiềm năng
        potential_pivots = pivot_data.get_potential_pivots() if hasattr(pivot_data, 'get_potential_pivots') else []
        if potential_pivots:
            status_info.append("\nĐiểm đang theo dõi:")
            for p in potential_pivots:
                status_info.append(f"- {p['type']} tại ${p['price']:,.2f} ({p['time']}) - Xác nhận: {p['confirmation_count']}/3")
        
        return status_info

    def analyze_price_action(self, current_price, last_pivot):
        """Phân tích price action"""
        if not last_pivot:
            return "Chưa có pivot để xác định xu hướng"
            
        price_diff = current_price - last_pivot['price']
        trend = "Uptrend" if price_diff > 0 else "Downtrend" if price_diff < 0 else "Sideway"
        return f"Xu hướng: {trend} (${abs(price_diff):,.2f} từ pivot cuối)"

    def save_test_results(self, df, results):
        """Lưu kết quả test vào Excel và vẽ biểu đồ"""
        try:
            # Thêm cột pivot_type vào DataFrame
            df['pivot_type'] = ''
            df['trend'] = ''
            
            # Đánh dấu các pivot đã xác nhận
            last_pivot_price = None
            for idx, row in df.iterrows():
                # Tìm pivot tại thời điểm này
                pivot = next((p for p in pivot_data.get_all_pivots() if p['time'] == row['time']), None)
                if pivot:
                    df.at[idx, 'pivot_type'] = pivot['type']
                    last_pivot_price = pivot['price']
                
                # Xác định xu hướng
                if last_pivot_price:
                    df.at[idx, 'trend'] = 'Uptrend' if row['price'] > last_pivot_price else 'Downtrend'
            
            with pd.ExcelWriter('test_results.xlsx', engine='xlsxwriter') as writer:
                # Sheet chính
                df.to_excel(writer, sheet_name='TestData', index=False)
                workbook = writer.book
                worksheet = writer.sheets['TestData']
                
                # Định dạng các cột
                price_format = workbook.add_format({'num_format': '$#,##0.00'})
                pivot_format = workbook.add_format({
                    'bold': True,
                    'font_color': 'red'
                })
                trend_format = workbook.add_format({
                    'bold': True
                })
                
                # Áp dụng định dạng
                worksheet.set_column('C:E', 12, price_format)
                worksheet.set_column('F:F', 15, pivot_format)
                worksheet.set_column('G:G', 15, trend_format)
                
                # Tạo biểu đồ
                chart = workbook.add_chart({'type': 'line'})
                chart.add_series({
                    'name': 'Price',
                    'categories': f"='TestData'!$B$2:$B${len(df) + 1}",
                    'values': f"='TestData'!$E$2:$E${len(df) + 1}"
                })
                
                # Định dạng biểu đồ
                chart.set_title({'name': 'Price and Pivots - Test Results'})
                chart.set_x_axis({'name': 'Time'})
                chart.set_y_axis({'name': 'Price'})
                chart.set_size({'width': 720, 'height': 400})
                
                # Thêm biểu đồ vào sheet
                worksheet.insert_chart('H2', chart)
                
                # Thêm thống kê
                stats_row = len(df) + 5
                worksheet.write(stats_row, 0, "Thống kê:")
                worksheet.write(stats_row + 1, 0, "Tổng số nến:")
                worksheet.write(stats_row + 1, 1, len(df))
                worksheet.write(stats_row + 2, 0, "Pivot đã xác nhận:")
                worksheet.write(stats_row + 2, 1, len(pivot_data.get_all_pivots()))

            self.log_message("\nĐã lưu kết quả test vào file test_results.xlsx", "SUCCESS")
            return True
            
        except Exception as e:
            self.log_message(f"Lỗi khi lưu Excel: {str(e)}", "ERROR")
            return False

    def run_test(self):
        """Chạy historical test cho S1"""
        try:
            # Set thời gian test
            current_time = datetime(2025, 3, 18, 3, 52, 11)
            start_time = datetime(2025, 3, 17, 0, 0, 0)
            
            self.log_message("\n=== Bắt đầu test S1 ===", "INFO")
            self.log_message(f"User: {self.user_login}")
            self.log_message(f"Thời gian bắt đầu: {start_time}")
            self.log_message(f"Thời gian kết thúc: {current_time}")
            
            # Lấy dữ liệu từ Binance
            klines = self.client.get_historical_klines(
                "BTCUSDT",
                Client.KLINE_INTERVAL_30MINUTE,
                start_str=int(start_time.timestamp() * 1000),
                end_str=int(current_time.timestamp() * 1000)
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
            
            initial_pivots = [
                {"time": "06:00", "type": "LL", "price": 81931},
                {"time": "11:00", "type": "LH", "price": 83843}
            ]
            
            for pivot in initial_pivots:
                if pivot_data.add_user_pivot(pivot["type"], pivot["price"], pivot["time"]):
                    self.log_message(f"✅ Đã thêm user pivot: {pivot['type']} tại ${pivot['price']} ({pivot['time']})", "SUCCESS")
                else:
                    self.log_message(f"❌ Không thể thêm user pivot: {pivot['type']} tại {pivot['time']}", "ERROR")
            
            # Chạy test
            self.log_message("\nBắt đầu phát hiện pivot...", "INFO")
            results = []
            
            for index, row in df.iterrows():
                price_data = {
                    'time': row['time'],
                    'price': row['price'],
                    'high': row['high'],
                    'low': row['low']
                }

                # Log chi tiết cho mỗi nến
                self.log_message(f"\n=== Phân tích nến {row['time']} ===", "INFO")
                self.log_message(f"Giá: ${row['price']:,.2f}")
                self.log_message(f"High: ${row['high']:,.2f}")
                self.log_message(f"Low: ${row['low']:,.2f}")
                
                # Thêm dữ liệu giá và xử lý
                pivot_data.add_price_data(price_data)
                
                # Kiểm tra pivot
                high_pivot = pivot_data.detect_pivot(row['high'], 'high')
                low_pivot = pivot_data.detect_pivot(row['low'], 'low')
                
                if high_pivot:
                    self.log_message(f"✅ Phát hiện pivot {high_pivot['type']} tại high (${high_pivot['price']:,.2f})", "SUCCESS")
                if low_pivot:
                    self.log_message(f"✅ Phát hiện pivot {low_pivot['type']} tại low (${low_pivot['price']:,.2f})", "SUCCESS")
                
                # Log trạng thái pivot
                status_info = self.get_pivot_status()
                for info in status_info:
                    self.log_message(info, "STATUS")
                
                # Log xu hướng
                all_pivots = pivot_data.get_all_pivots()
                if all_pivots:
                    last_pivot = all_pivots[-1]
                    trend_info = self.analyze_price_action(row['price'], last_pivot)
                    self.log_message(trend_info, "TREND")
                
                # Cập nhật results
                for pivot in all_pivots:
                    if pivot not in results:
                        results.append(pivot)
            
            # Tổng kết kết quả
            self.log_message("\n=== Tổng kết kết quả ===", "SUMMARY")
            self.log_message(f"Tổng số nến: {len(df)}")
            self.log_message(f"Tổng số pivot đã xác nhận: {len(results)}")
            
            if results:
                self.log_message("\nDanh sách pivot đã xác nhận:")
                for pivot in results:
                    self.log_message(f"- {pivot['type']} tại ${pivot['price']:,.2f} ({pivot['time']})")
            
            # Lưu kết quả vào Excel
            self.save_test_results(df, results)
            
            return results
            
        except Exception as e:
            error_msg = f"❌ Lỗi khi chạy test: {str(e)}"
            self.log_message(error_msg, "ERROR")
            return None

# Entry point
if __name__ == "__main__":
    tester = S1HistoricalTester()
    print("Đang chạy historical test cho S1...")
    results = tester.run_test()
    print("\nTest hoàn tất! Kiểm tra file debug_historical_test.log và test_results.xlsx để xem chi tiết.")
