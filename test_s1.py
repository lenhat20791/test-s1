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
utc_time = "2025-03-19 02:49:51"  # UTC time
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

    def log_message(self, message):
        """Ghi log ra console và file"""
        print(message)
        with open(self.debug_log_file, "a", encoding="utf-8") as f:
            f.write(f"{message}\n")

    def save_test_results(self, df, results):
        """Lưu kết quả test vào Excel và vẽ biểu đồ"""
        try:
            # Thêm cột pivot_type vào DataFrame
            df['pivot_type'] = ''
            
            # Đánh dấu các pivot đã xác nhận
            for pivot in pivot_data.get_all_pivots():
                mask = (df['time'] == pivot['time'])
                df.loc[mask, 'pivot_type'] = pivot['type']
            
            # Tạo DataFrame cho confirmed pivots
            confirmed_data = []
            seen_pivots = set()

            for pivot in pivot_data.get_all_pivots():
                pivot_key = (pivot['time'], pivot['type'], pivot['price'])
                if pivot_key not in seen_pivots:
                    confirmed_data.append({
                        'Time': pivot['time'],
                        'Type': pivot['type'],
                        'Price': pivot['price']
                    })
                    seen_pivots.add(pivot_key)

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
                
                # Áp dụng định dạng
                worksheet.set_column('C:E', 12, price_format)
                worksheet.set_column('F:F', 15, pivot_format)
                
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
                worksheet.write(stats_row + 1, 0, "Tổng số pivot:")
                worksheet.write(stats_row + 1, 1, len(pivot_data.get_all_pivots()))
                worksheet.write(stats_row + 2, 0, "Pivot đã xác nhận:")
                worksheet.write(stats_row + 2, 1, len(pivot_data.get_all_pivots()))

            self.log_message("\nĐã lưu kết quả test vào file test_results.xlsx")
            return True
            
        except Exception as e:
            self.log_message(f"❌ Lỗi khi lưu Excel: {str(e)}")
            return False

    def run_test(self):
        """Chạy historical test cho S1"""
        try:
            # Set thời gian test
            current_time = datetime(2025, 3, 18, 3, 52, 11)
            start_time = datetime(2025, 3, 17, 0, 0, 0)
            
            self.log_message(f"\n=== Bắt đầu test S1 ===")
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
                self.log_message("Không tìm thấy dữ liệu cho khoảng thời gian này")
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
            
            self.log_message(f"\nTổng số nến: {len(df)}")
            
            # Reset trạng thái và thêm pivots đã biết
            pivot_data.clear_all()
            
            initial_pivots = [
                {"time": "06:00", "type": "LL", "price": 81931},
                {"time": "11:00", "type": "LH", "price": 83843}
            ]
            
            for pivot in initial_pivots:
                if pivot_data.add_user_pivot(pivot["type"], pivot["price"], pivot["time"]):
                    self.log_message(f"✅ Đã thêm user pivot: {pivot['type']} tại ${pivot['price']} ({pivot['time']})")
                else:
                    self.log_message(f"❌ Không thể thêm user pivot: {pivot['type']} tại {pivot['time']}")
            
            # Chạy test
            self.log_message("\nBắt đầu phát hiện pivot...")
            results = []
            
            for index, row in df.iterrows():
                price_data = {
                    'time': row['time'],
                    'price': row['price'],
                    'high': row['high'],
                    'low': row['low']
                }

                # Log chi tiết cho mỗi nến
                self.log_message(f"\n=== Phân tích nến {row['time']} ===")
                self.log_message(f"Giá: ${row['price']:,.2f}")
                self.log_message(f"High: ${row['high']:,.2f}")
                self.log_message(f"Low: ${row['low']:,.2f}")
                
                # Thêm dữ liệu giá và xử lý
                pivot_data.add_price_data(price_data)
                
                # Kiểm tra pivot
                high_pivot = pivot_data.detect_pivot(row['high'], 'high')
                low_pivot = pivot_data.detect_pivot(row['low'], 'low')
                
                if high_pivot:
                    self.log_message(f"✅ Phát hiện pivot {high_pivot['type']} tại high (${high_pivot['price']:,.2f})")
                if low_pivot:
                    self.log_message(f"✅ Phát hiện pivot {low_pivot['type']} tại low (${low_pivot['price']:,.2f})")
                
                # Log kết quả
                all_pivots = pivot_data.get_all_pivots()
                if all_pivots:
                    last_pivot = all_pivots[-1]
                    for pivot in all_pivots:
                        if pivot not in results:
                            results.append(pivot)
            
            # Tổng kết kết quả
            self.log_message("\n=== Tổng kết kết quả ===")
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
            self.log_message(error_msg)
            return None

# Entry point
if __name__ == "__main__":
    tester = S1HistoricalTester()
    print("Đang chạy historical test cho S1...")
    results = tester.run_test()
    print("\nTest hoàn tất! Kiểm tra file debug_historical_test.log và test_results.xlsx để xem chi tiết.")
