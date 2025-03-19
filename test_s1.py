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
utc_time = "2025-03-18 09:38:38"
utc = pytz.UTC
vietnam_tz = pytz.timezone('Asia/Ho_Chi_Minh')

# Parse UTC time và chuyển sang múi giờ Việt Nam
utc_dt = datetime.strptime(utc_time, '%Y-%m-%d %H:%M:%S').replace(tzinfo=utc)
vietnam_time = utc_dt.astimezone(vietnam_tz)
current_time = vietnam_time.strftime('%Y-%m-%d %H:%M:%S')

current_user = "lenhat20791"
DEBUG_LOG_FILE = "debug_historical_test.log"

print(f"Current Date and Time (UTC - YYYY-MM-DD HH:MM:SS formatted): {current_time}")
print(f"Current User's Login: {current_user}")
set_current_time_and_user(current_time, current_user)

# Lưu thông tin vào s1.py
set_current_time_and_user(current_time, current_user)

class S1HistoricalTester:
    def __init__(self, user_login="lenhat20791"):
        self.client = Client()
        self.debug_log_file = "debug.log" 
        self.user_login = user_login
        self.clear_log_file()
        
    def clear_log_file(self):
        """Xóa nội dung của file log để bắt đầu test mới"""
        try:
            # Mở file ở mode 'w' sẽ xóa nội dung cũ và tạo file mới nếu chưa tồn tại
            with open(self.debug_log_file, 'w') as f:
                f.write('')  # Write empty string to clear file
        except Exception as e:
            print(f"Error clearing log file: {str(e)}")
    def log_message(self, message):
        """Ghi log ra console và file"""
        print(message)
        with open(self.debug_log_file, "a", encoding="utf-8") as f:
            f.write(f"{message}\n")

    def add_known_pivots(self):
        """Thêm các pivot đã biết từ dữ liệu thực"""
        user_pivots = [
            {"time": "06:00", "type": "LL", "price": 81931},
            {"time": "11:00", "type": "LH", "price": 83843}
        ]
        
        for pivot in user_pivots:
            if pivot_data.add_user_pivot(pivot["type"], pivot["price"], pivot["time"]):
                self.log_message(f"✅ Đã thêm user pivot: {pivot['type']} tại ${pivot['price']} ({pivot['time']})")
            else:
                self.log_message(f"❌ Không thể thêm user pivot: {pivot['type']} tại {pivot['time']}")

    def save_test_results(self, df, results):
        """Lưu kết quả test vào Excel và vẽ biểu đồ"""
        try:
            # Thêm cột pivot_type và pending_status vào DataFrame
            df['pivot_type'] = ''
            
            # Đánh dấu các pivot đã xác nhận
            for pivot in pivot_data.get_all_pivots():
                mask = (df['time'] == pivot['time'])
                df.loc[mask, 'pivot_type'] = pivot['type']
            
            # Tạo DataFrame cho confirmed pivots và loại bỏ trùng lặp
            confirmed_data = []
            seen_pivots = set()  # Set để theo dõi các pivot đã thấy

            for pivot in pivot_data.confirmed_pivots:
                # Tạo tuple key để kiểm tra trùng lặp
                pivot_key = (pivot['time'], pivot['type'], pivot['price'])
                
                # Chỉ thêm pivot nếu chưa tồn tại
                if pivot_key not in seen_pivots:
                    confirmed_data.append({
                        'Time': pivot['time'],
                        'Type': pivot['type'],
                        'Price': pivot['price']
                    })
                    seen_pivots.add(pivot_key)

            # Tạo DataFrame và sắp xếp theo thời gian
            df_confirmed = pd.DataFrame(confirmed_data)
            if not df_confirmed.empty:
                # Chuyển đổi cột Time sang datetime để sắp xếp
                df_confirmed['Time_sort'] = pd.to_datetime(df_confirmed['Time'], format='%H:%M')
                df_confirmed = df_confirmed.sort_values('Time_sort')
                df_confirmed = df_confirmed.drop('Time_sort', axis=1)  # Xóa cột phụ sau khi sắp xếp
            
            # Lưu vào Excel với xlsxwriter
            with pd.ExcelWriter('test_results.xlsx', engine='xlsxwriter') as writer:
                # Sheet chính 
                df.to_excel(writer, sheet_name='TestData', index=False)
                
                # Sheet Confirmed Pivots
                if not df_confirmed.empty:
                    df_confirmed.to_excel(writer, sheet_name='ConfirmedPivots', index=False)
                
                # Lấy workbook và worksheet
                workbook = writer.book
                worksheet = writer.sheets['TestData']
                
                # Định dạng cho các cột
                price_format = workbook.add_format({'num_format': '$#,##0.00'})
                pivot_format = workbook.add_format({
                    'bold': True,
                    'font_color': 'red'
                })
                pending_format = workbook.add_format({
                    'font_color': 'blue',
                    'italic': True
                })
                
                # Áp dụng định dạng cho TestData sheet
                worksheet.set_column('C:E', 12, price_format)  # high, low, price columns
                worksheet.set_column('F:F', 15, pivot_format)  # pivot_type column
                worksheet.set_column('G:G', 20, pending_format)  # pending_status column
                
                # Định dạng cho ConfirmedPivots sheet nếu có
                if not df_confirmed.empty:
                    confirmed_worksheet = writer.sheets['ConfirmedPivots']
                    confirmed_worksheet.set_column('C:C', 12, price_format)  # Price column
                
                # Tạo biểu đồ
                chart = workbook.add_chart({'type': 'line'})
                
                # Thêm series với tên sheet đã được quote
                chart.add_series({
                    'name': 'Price',
                    'categories': f"='TestData'!$B$2:$B${len(df) + 1}",
                    'values': f"='TestData'!$E$2:$E${len(df) + 1}"
                })
                
                # Định dạng biểu đồ
                chart.set_title({'name': 'Price and Pivots - Test Results'})
                chart.set_x_axis({'name': 'Time'})
                chart.set_y_axis({'name': 'Price'})
                
                # Chèn biểu đồ vào worksheet
                worksheet.insert_chart('I2', chart)
                
                # Thêm thống kê
                stats_row = len(df) + 5
                worksheet.write(stats_row, 0, "Thống kê:")
                worksheet.write(stats_row + 1, 0, "Tổng số pivot:")
                worksheet.write(stats_row + 1, 1, len(pivot_data.get_all_pivots()))
                worksheet.write(stats_row + 2, 0, "Pivot đã xác nhận:")
                worksheet.write(stats_row + 2, 1, len(pivot_data.confirmed_pivots))
                worksheet.write(stats_row + 3, 0, "Pivot đang chờ xác nhận:")
                worksheet.write(stats_row + 3, 1, len(pivot_data.pending_pivots))

            self.log_message("\nĐã lưu kết quả test vào file test_results.xlsx")
            return True
            
        except Exception as e:
            self.log_message(f"❌ Lỗi khi lưu Excel: {str(e)}")
            return False

    def analyze_pivot_points(self, df, time_str):
        try:
            row_idx = df[df['time'] == time_str].index[0]
            row = df.iloc[row_idx]
            
            self.log_message(f"\n=== Phân tích chi tiết tại {time_str} ===")
            self.log_message(f"Nến hiện tại:")
            self.log_message(f"High: ${row['high']:,.2f}")
            self.log_message(f"Low: ${row['low']:,.2f}")
            self.log_message(f"Close: ${row['price']:,.2f}")
            
            # Kiểm tra điều kiện pivot
            all_pivots = pivot_data.get_all_pivots()
            if all_pivots:
                last_pivot = all_pivots[-1]
                last_time = datetime.strptime(last_pivot["time"], "%H:%M")
                current_time = datetime.strptime(row['time'], "%H:%M")
                time_diff = (current_time - last_time).total_seconds() / 1800
                price_change = abs(row['price'] - last_pivot["price"]) / last_pivot["price"]
                
                self.log_message(f"\nSo sánh với pivot trước:")
                self.log_message(f"- Pivot trước: {last_pivot['type']} tại ${last_pivot['price']:,.2f} ({last_pivot['time']})")
                self.log_message(f"- Khoảng cách: {time_diff:.1f} nến")
                self.log_message(f"- Biên độ giá: {price_change:.2%}")
                    
        except Exception as e:
            self.log_message(f"❌ Lỗi khi phân tích pivot point: {str(e)}")

    def run_test(self):
        """Chạy historical test cho S1"""
        try:
            # Set thời gian test từ 00:00 17/03 đến hiện tại
            current_time = datetime(2025, 3, 18, 3, 52, 11)    # Current time from input
            start_time = datetime(2025, 3, 17, 0, 0, 0)       # Start from 00:00 17/03
            
            self.log_message(f"\n=== Bắt đầu test S1 ===")
            self.log_message(f"User: {self.user_login}")
            self.log_message(f"Thời gian bắt đầu: {start_time}")
            self.log_message(f"Thời gian kết thúc: {current_time}")
            
            # Lấy dữ liệu từ Binance
            klines = self.client.get_historical_klines(
                "BTCUSDT",  # Futures
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
            
            # Xử lý dữ liệu
            df['datetime'] = pd.to_datetime(df['timestamp'], unit='ms')
            df['time'] = df['datetime'].dt.strftime('%H:%M')
            df = df[['datetime', 'time', 'high', 'low', 'close']]
            df = df.rename(columns={'close': 'price'})
            
            for col in ['high', 'low', 'price']:
                df[col] = df[col].astype(float)
            
            self.log_message(f"\nTổng số nến: {len(df)}")
            
            # Reset trạng thái S1 và thêm các pivot đã biết
            pivot_data.clear_all()
            
            # Thêm 2 pivot points đã biết
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
            
            # Các thời điểm quan trọng cần phân tích chi tiết
            important_times = ['06:00', '11:00']
            
            for index, row in df.iterrows():
                price_data = {
                    'time': row['time'],
                    'price': row['price'],
                    'high': row['high'],
                    'low': row['low']
                }
                
                # Log số pending pivots hiện tại
                self.log_message(f"\nSố pending pivots: {len(pivot_data.pending_pivots)}")
                
                # Log chi tiết pending pivots
                if pivot_data.pending_pivots:
                    self.log_message("Chi tiết pending pivots:")
                    for p in pivot_data.pending_pivots:
                        self.log_message(f"- Type: {p['type']}, Price: ${p['price']:,.2f}, Confirmations: {p['confirmation_candles']}/3")
                        if p['type'] in ["H", "HH", "LH"]:
                            self.log_message(f"  Giá cao nhất: ${p['highest_price']:,.2f}")
                            self.log_message(f"  Thời gian cao nhất: {p['highest_time']}")
                            self.log_message(f"  Số nến thấp hơn: {p['lower_prices']}")
                        else:
                            self.log_message(f"  Giá thấp nhất: ${p['lowest_price']:,.2f}")
                            self.log_message(f"  Thời gian thấp nhất: {p['lowest_time']}")
                            self.log_message(f"  Số nến cao hơn: {p['higher_prices']}")
                
                # Phân tích chi tiết tại các thời điểm quan trọng
                if row['time'] in important_times:
                    self.analyze_pivot_points(df, row['time'])
                
                # Thêm dữ liệu giá và xử lý
                pivot_data.add_price_data(price_data)
                
                # Log kết quả kiểm tra high/low
                high_pivot = pivot_data.detect_pivot(row['high'], 'H')
                low_pivot = pivot_data.detect_pivot(row['low'], 'L')
                self.log_message(f"Checking High: ${row['high']:,.2f} -> Result: {high_pivot}")
                self.log_message(f"Checking Low: ${row['low']:,.2f} -> Result: {low_pivot}")
                
                # Log điều kiện thêm pivot
                all_pivots = pivot_data.get_all_pivots()
                if all_pivots:
                    last_pivot = all_pivots[-1]
                    last_time = datetime.strptime(last_pivot["time"], "%H:%M")
                    current_time = datetime.strptime(row['time'], "%H:%M")
                    time_diff = (current_time - last_time).total_seconds() / 1800
                    price_change = abs(row['price'] - last_pivot["price"]) / last_pivot["price"]
                    
                    self.log_message("\nKiểm tra điều kiện thêm pivot:")
                    self.log_message(f"Khoảng cách thời gian: {time_diff:.1f} nến")
                    self.log_message(f"Biên độ giá: {price_change:.2%}")
                    self.log_message(f"So với pivot trước ({last_pivot['type']} at {last_pivot['time']})")
                
                # Cập nhật results với các pivot đã xác nhận
                all_pivots = pivot_data.get_all_pivots()
                for pivot in all_pivots:
                    if pivot not in results:
                        results.append(pivot)
            
            # Tổng kết kết quả
            self.log_message("\n=== Tổng kết kết quả ===")
            self.log_message(f"Tổng số nến: {len(df)}")
            self.log_message(f"Tổng số pivot đã xác nhận: {len(results)}")
            self.log_message(f"Số pivot đang chờ xác nhận: {len(pivot_data.pending_pivots)}")
            
            if results:
                self.log_message("\nDanh sách pivot đã xác nhận:")
                for pivot in results:
                    self.log_message(f"\nThời gian: {pivot['time']}")
                    self.log_message(f"Loại: {pivot['type']}")
                    self.log_message(f"Giá: ${pivot['price']:,.2f}")
            
            if pivot_data.pending_pivots:
                self.log_message("\nDanh sách pivot đang chờ xác nhận:")
                for pivot in pivot_data.pending_pivots:
                    self.log_message(f"\nThời gian: {pivot['time']}")
                    self.log_message(f"Loại: {pivot['type']}")
                    self.log_message(f"Giá ban đầu: ${pivot['price']:,.2f}")
                    self.log_message(f"Xác nhận: {pivot['confirmation_candles']}/3")
                    if pivot['type'] in ["H", "HH", "LH"]:
                        self.log_message(f"Giá cao nhất: ${pivot['highest_price']:,.2f}")
                        self.log_message(f"Thời gian cao nhất: {pivot['highest_time']}")
                        self.log_message(f"Số nến thấp hơn: {pivot['lower_prices']}")
                    else:
                        self.log_message(f"Giá thấp nhất: ${pivot['lowest_price']:,.2f}")
                        self.log_message(f"Thời gian thấp nhất: {pivot['lowest_time']}")
                        self.log_message(f"Số nến cao hơn: {pivot['higher_prices']}")
            
            # Lưu kết quả vào Excel
            self.save_test_results(df, results)
            
            return results
            
        except Exception as e:
            error_msg = f"❌ Lỗi khi chạy test: {str(e)}"
            self.log_message(error_msg)
            return None
    
    def test_pivot_rules(self):
        """Test các quy tắc pivot mới"""
        try:
            # Reset trạng thái pivot_data
            pivot_data.clear_all()
            
            # Dữ liệu test theo thời gian tăng dần
            test_data = [
                # Test case 1: Xác nhận LL
                {"time": "09:00", "price": 82000, "high": 82000, "low": 81800},  # Nến thấp tiềm năng
                {"time": "09:30", "price": 82200, "high": 82300, "low": 82000},  # Nến cao hơn 1
                {"time": "10:00", "price": 82300, "high": 82400, "low": 82100},  # Nến cao hơn 2
                {"time": "10:30", "price": 82400, "high": 82500, "low": 82200},  # Nến cao hơn 3
                
                # Test case 2: Xác nhận HH sau LL
                {"time": "11:00", "price": 83000, "high": 83100, "low": 82800},  # Nến cao tiềm năng
                {"time": "11:30", "price": 82800, "high": 82900, "low": 82700},  # Nến thấp hơn 1
                {"time": "12:00", "price": 82700, "high": 82800, "low": 82600},  # Nến thấp hơn 2
                {"time": "12:30", "price": 82600, "high": 82700, "low": 82500},  # Nến thấp hơn 3
                
                # Test case 3: Xác nhận LH 
                {"time": "13:00", "price": 82500, "high": 82600, "low": 82400},  # Nến cao tiềm năng
                {"time": "13:30", "price": 82700, "high": 82800, "low": 82600},  # Nến cao hơn 1
                {"time": "14:00", "price": 82900, "high": 83000, "low": 82800},  # Nến cao hơn 2
                {"time": "14:30", "price": 83100, "high": 83200, "low": 83000},  # Nến cao hơn 3
                
                # Test case 4: Xác nhận HL
                {"time": "15:00", "price": 82400, "high": 82500, "low": 82300},  # Nến thấp tiềm năng
                {"time": "15:30", "price": 82200, "high": 82300, "low": 82100},  # Nến thấp hơn 1
                {"time": "16:00", "price": 82100, "high": 82200, "low": 82000},  # Nến thấp hơn 2
                {"time": "16:30", "price": 82000, "high": 82100, "low": 81900},  # Nến thấp hơn 3
            ]

            self.log_message("\n=== Bắt đầu test quy tắc pivot ===")
            self.log_message(f"Thời gian hiện tại: {pivot_data.current_time}")
            self.log_message(f"User: {pivot_data.current_user}")
            self.log_message("="*50)
            
            for data in test_data:
                # Xử lý dữ liệu giá
                pivot_data.add_price_data(data)
                
                # Kiểm tra pivot tại high và low
                high_pivot = pivot_data.detect_pivot(data["high"], "high")
                low_pivot = pivot_data.detect_pivot(data["low"], "low")
                
                # Log kết quả kiểm tra
                self.log_message(f"\n=== Phân tích tại {data['time']} ===")
                self.log_message("📊 Dữ liệu giá:")
                self.log_message(f"  - Giá đóng cửa: ${data['price']:,.2f}")
                self.log_message(f"  - Giá cao nhất:  ${data['high']:,.2f}")
                self.log_message(f"  - Giá thấp nhất: ${data['low']:,.2f}")

                # Log kết quả kiểm tra pivot
                self.log_message("\n🔍 Kết quả kiểm tra pivot:")
                self.log_message(f"  - High: ${data['high']:,.2f} → {high_pivot if high_pivot else '❌ Không phải pivot'}")
                self.log_message(f"  - Low:  ${data['low']:,.2f} → {low_pivot if low_pivot else '❌ Không phải pivot'}")

                # Log danh sách pivot đã xác nhận
                confirmed_pivots = pivot_data.get_all_pivots()
                if confirmed_pivots:
                    self.log_message("\n✅ Pivot đã xác nhận:")
                    for pivot in confirmed_pivots:
                        # Thêm màu sắc cho các loại pivot khác nhau
                        pivot_symbol = {
                            'HH': '🟢',  # Xanh lá
                            'LL': '🔴',  # Đỏ
                            'LH': '🔵',  # Xanh dương
                            'HL': '🟡'   # Vàng
                        }.get(pivot['type'], '⚪')  # Mặc định trắng
                        
                        # Tính % thay đổi so với giá hiện tại
                        price_change = ((data['price'] - pivot['price']) / pivot['price']) * 100
                        
                        self.log_message(f"  {pivot_symbol} {pivot['type']} tại ${pivot['price']:,.2f} ({pivot['time']}) | {price_change:+.2f}% so với giá hiện tại")

                    # Thêm thống kê
                    self.log_message(f"\n📈 Tổng số pivot đã xác nhận: {len(confirmed_pivots)}")
                else:
                    self.log_message("\nℹ️ Chưa có pivot nào được xác nhận")

                self.log_message("="*50)

            # Kiểm tra kết quả cuối cùng
            confirmed_pivots = pivot_data.get_all_pivots()
            self.log_message("\n=== Tổng kết kết quả test ===")
            self.log_message(f"Số pivot đã xác nhận: {len(confirmed_pivots)}")
            
            if confirmed_pivots:
                self.log_message("\nDanh sách pivot theo thứ tự thời gian:")
                for pivot in confirmed_pivots:
                    self.log_message(f"- {pivot['type']} tại ${pivot['price']:,.2f} ({pivot['time']})")
            
            # Kiểm tra thứ tự các pivot đã xác nhận
            expected_sequence = ["LL", "HH", "LH", "HL"]
            actual_sequence = [p["type"] for p in confirmed_pivots]
            
            if actual_sequence == expected_sequence:
                self.log_message("\n✅ Test thành công: Thứ tự pivot đúng")
                self.log_message(f"Chuỗi pivot mong đợi: {' → '.join(expected_sequence)}")
                self.log_message(f"Chuỗi pivot thực tế:  {' → '.join(actual_sequence)}")
            else:
                self.log_message("\n❌ Test thất bại: Thứ tự pivot không đúng")
                self.log_message(f"Chuỗi pivot mong đợi: {' → '.join(expected_sequence)}")
                self.log_message(f"Chuỗi pivot thực tế:  {' → '.join(actual_sequence)}")
                
            return True

        except Exception as e:
            self.log_message(f"❌ Lỗi khi chạy test: {str(e)}")
            return False
    
def test_current_time_and_user():
    """Test chuyển đổi múi giờ và user"""
    utc_time = "2025-03-19 01:58:19"
    test_user = "lenhat20791"
    
    set_current_time_and_user(utc_time, test_user)
    
    # Kiểm tra chuyển đổi múi giờ
    assert "GMT+7" in pivot_data.current_time
    assert pivot_data.current_user == test_user
    
    def test_time_format():
        current_time = "2025-03-18 05:26:50"
        time_pattern = r'\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2}'
        assert re.match(time_pattern, current_time)
        # Kiểm tra xem có thể parse được thành datetime object
        datetime.strptime(current_time, '%Y-%m-%d %H:%M:%S')

    def test_user():
        current_user = "lenhat20791"
        assert isinstance(current_user, str)
        assert len(current_user) > 0
        
    def clear_log_file(self):
        """Xóa nội dung file log cũ"""
        Path(self.debug_log_file).write_text("")
        
    def log_message(self, message):
        """Ghi log ra console và file"""
        print(message)
        with open(self.debug_log_file, "a", encoding="utf-8") as f:
            f.write(f"{message}\n")

    def add_known_pivots(self):
        """Thêm các pivot đã biết từ dữ liệu thực"""
        user_pivots = [
            {"time": "06:00", "type": "LL", "price": 81931},
            {"time": "11:00", "type": "LH", "price": 83843}
        ]
        
        for pivot in user_pivots:
            if pivot_data.add_user_pivot(pivot["type"], pivot["price"], pivot["time"]):
                self.log_message(f"✅ Đã thêm user pivot: {pivot['type']} tại ${pivot['price']} ({pivot['time']})")
            else:
                self.log_message(f"❌ Không thể thêm user pivot: {pivot['type']} tại {pivot['time']}")

    def save_test_results(self, df, results):
        """Lưu kết quả test vào Excel và vẽ biểu đồ"""
        try:
            # Thêm cột pivot_type và pending_status vào DataFrame
            df['pivot_type'] = ''
            df['pending_status'] = ''
            
            # Đánh dấu các pivot đã xác nhận
            for pivot in pivot_data.get_all_pivots():
                mask = (df['time'] == pivot['time'])
                df.loc[mask, 'pivot_type'] = pivot['type']
            
            # Đánh dấu các pending pivots
            for pivot in pivot_data.pending_pivots:
                mask = (df['time'] == pivot['time'])
                df.loc[mask, 'pending_status'] = f"Pending {pivot['type']} ({pivot['confirmation_candles']}/3)"
            
            # Lưu vào Excel
            writer = pd.ExcelWriter('test_results.xlsx', engine='xlsxwriter')
            df.to_excel(writer, sheet_name='Test Data', index=False)
            
            # Tạo workbook và worksheet
            workbook = writer.book
            worksheet = writer.sheets['Test Data']
            
            # Định dạng cho các cột
            price_format = workbook.add_format({'num_format': '$#,##0.00'})
            pivot_format = workbook.add_format({'bold': True, 'color': 'red'})
            pending_format = workbook.add_format({'color': 'blue', 'italic': True})
            
            # Áp dụng định dạng
            worksheet.set_column('C:E', 12, price_format)  # high, low, price columns
            worksheet.set_column('F:F', 15, pivot_format)  # pivot_type column
            worksheet.set_column('G:G', 20, pending_format)  # pending_status column
            
            # Tạo biểu đồ
            chart = workbook.add_chart({'type': 'line'})
            
            # Thêm series price
            chart.add_series({
                'name': 'Price',
                'categories': '=Test Data!$B$2:$B$' + str(len(df) + 1),
                'values': '=Test Data!$E$2:$E$' + str(len(df) + 1),
            })
            
            # Định dạng biểu đồ
            chart.set_title({'name': 'Price and Pivots - Test Results'})
            chart.set_x_axis({'name': 'Time'})
            chart.set_y_axis({'name': 'Price'})
            
            # Chèn biểu đồ vào worksheet
            worksheet.insert_chart('I2', chart)
            
            writer.close()
            self.log_message("\nĐã lưu kết quả test vào file test_results.xlsx")
            return True
            
        except Exception as e:
            self.log_message(f"❌ Lỗi khi lưu Excel: {str(e)}")
            return False

    def analyze_pivot_points(self, df, time_str):
        """Phân tích chi tiết tại thời điểm cụ thể"""
        try:
            row_idx = df[df['time'] == time_str].index[0]
            row = df.iloc[row_idx]
            
            self.log_message(f"\n=== Phân tích chi tiết tại {time_str} ===")
            self.log_message(f"Nến hiện tại:")
            self.log_message(f"High: ${row['high']:,.2f}")
            self.log_message(f"Low: ${row['low']:,.2f}")
            self.log_message(f"Close: ${row['price']:,.2f}")
            
            # Lấy 3 nến trước đó để phân tích xác nhận
            if row_idx >= 3:
                self.log_message(f"\n3 nến trước (cho xác nhận):")
                for i in range(3):
                    prev = df.iloc[row_idx-i-1]
                    self.log_message(f"{prev['time']}:")
                    self.log_message(f"High: ${prev['high']:,.2f}")
                    self.log_message(f"Low: ${prev['low']:,.2f}")
                    self.log_message(f"Close: ${prev['price']:,.2f}")
            
            # Phân tích pending pivots
            if pivot_data.pending_pivots:
                self.log_message("\nPending Pivots hiện tại:")
                for p in pivot_data.pending_pivots:
                    self.log_message(f"- Type: {p['type']}")
                    self.log_message(f"  Giá ban đầu: ${p['price']:,.2f}")
                    self.log_message(f"  Thời gian: {p['time']}")
                    self.log_message(f"  Xác nhận: {p['confirmation_candles']}/3")
                    
                    if p['type'] in ["H", "HH", "LH"]:
                        self.log_message(f"  Giá cao nhất: ${p['highest_price']:,.2f}")
                        self.log_message(f"  Tại: {p['highest_time']}")
                        self.log_message(f"  Số nến thấp hơn: {p['lower_prices']}")
                    else:
                        self.log_message(f"  Giá thấp nhất: ${p['lowest_price']:,.2f}")
                        self.log_message(f"  Tại: {p['lowest_time']}")
                        self.log_message(f"  Số nến cao hơn: {p['higher_prices']}")
            
            # Kiểm tra điều kiện pivot
            all_pivots = pivot_data.get_all_pivots()
            if all_pivots:
                last_pivot = all_pivots[-1]
                last_time = datetime.strptime(last_pivot["time"], "%H:%M")
                current_time = datetime.strptime(row['time'], "%H:%M")
                time_diff = (current_time - last_time).total_seconds() / 1800  # Chuyển sang số nến 30m
                price_change = abs(row['price'] - last_pivot["price"]) / last_pivot["price"]
                
                self.log_message(f"\nSo sánh với pivot trước:")
                self.log_message(f"- Pivot trước: {last_pivot['type']} tại ${last_pivot['price']:,.2f} ({last_pivot['time']})")
                self.log_message(f"- Khoảng cách: {time_diff:.1f} nến")
                self.log_message(f"- Biên độ giá: {price_change:.2%}")
                
        except Exception as e:
            self.log_message(f"❌ Lỗi khi phân tích pivot point: {str(e)}")

    def run_test(self):
        """Chạy historical test cho S1"""
        try:
            # Set thời gian test từ 00:00 17/03 đến hiện tại
            current_time = datetime(2025, 3, 18, 3, 52, 11)    # Current time from input
            start_time = datetime(2025, 3, 17, 0, 0, 0)       # Start from 00:00 17/03
            
            self.log_message(f"\n=== Bắt đầu test S1 ===")
            self.log_message(f"User: {self.user_login}")
            self.log_message(f"Thời gian bắt đầu: {start_time}")
            self.log_message(f"Thời gian kết thúc: {current_time}")
            
            # Lấy dữ liệu từ Binance
            klines = self.client.get_historical_klines(
                "BTCUSDT",  # Futures
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
            
            # Xử lý dữ liệu
            df['datetime'] = pd.to_datetime(df['timestamp'], unit='ms')
            df['time'] = df['datetime'].dt.strftime('%H:%M')
            df = df[['datetime', 'time', 'high', 'low', 'close']]
            df = df.rename(columns={'close': 'price'})
            
            for col in ['high', 'low', 'price']:
                df[col] = df[col].astype(float)
            
            self.log_message(f"\nTổng số nến: {len(df)}")
            
            # Reset trạng thái S1 và thêm các pivot đã biết
            pivot_data.clear_all()
            
            # Thêm 2 pivot points đã biết
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
            
            # Các thời điểm quan trọng cần phân tích chi tiết
            important_times = ['06:00', '11:00']
            
            for index, row in df.iterrows():
                price_data = {
                    'time': row['time'],
                    'price': row['price'],
                    'high': row['high'],
                    'low': row['low']
                }
                
                # Log số pending pivots hiện tại
                self.log_message(f"\nSố pending pivots: {len(pivot_data.pending_pivots)}")
                
                # Log chi tiết pending pivots
                if pivot_data.pending_pivots:
                    self.log_message("Chi tiết pending pivots:")
                    for p in pivot_data.pending_pivots:
                        self.log_message(f"- Type: {p['type']}, Price: ${p['price']:,.2f}, Confirmations: {p['confirmation_candles']}/3")
                        if p['type'] in ["H", "HH", "LH"]:
                            self.log_message(f"  Giá cao nhất: ${p['highest_price']:,.2f}")
                            self.log_message(f"  Thời gian cao nhất: {p['highest_time']}")
                            self.log_message(f"  Số nến thấp hơn: {p['lower_prices']}")
                        else:
                            self.log_message(f"  Giá thấp nhất: ${p['lowest_price']:,.2f}")
                            self.log_message(f"  Thời gian thấp nhất: {p['lowest_time']}")
                            self.log_message(f"  Số nến cao hơn: {p['higher_prices']}")
                
                # Phân tích chi tiết tại các thời điểm quan trọng
                if row['time'] in important_times:
                    self.analyze_pivot_points(df, row['time'])
                
                # Thêm dữ liệu giá và xử lý
                pivot_data.add_price_data(price_data)
                
                # Log kết quả kiểm tra high/low
                high_pivot = pivot_data.detect_pivot(row['high'], 'H')
                low_pivot = pivot_data.detect_pivot(row['low'], 'L')
                self.log_message(f"Checking High: ${row['high']:,.2f} -> Result: {high_pivot}")
                self.log_message(f"Checking Low: ${row['low']:,.2f} -> Result: {low_pivot}")
                
                # Log điều kiện thêm pivot
                all_pivots = pivot_data.get_all_pivots()
                if all_pivots:
                    last_pivot = all_pivots[-1]
                    last_time = datetime.strptime(last_pivot["time"], "%H:%M")
                    current_time = datetime.strptime(row['time'], "%H:%M")
                    time_diff = (current_time - last_time).total_seconds() / 1800
                    price_change = abs(row['price'] - last_pivot["price"]) / last_pivot["price"]
                    
                    self.log_message("\nKiểm tra điều kiện thêm pivot:")
                    self.log_message(f"Khoảng cách thời gian: {time_diff:.1f} nến")
                    self.log_message(f"Biên độ giá: {price_change:.2%}")
                    self.log_message(f"So với pivot trước ({last_pivot['type']} at {last_pivot['time']})")
                
                # Cập nhật results với các pivot đã xác nhận
                all_pivots = pivot_data.get_all_pivots()
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
                    self.log_message(f"\nThời gian: {pivot['time']}")
                    self.log_message(f"Loại: {pivot['type']}")
                    self.log_message(f"Giá: ${pivot['price']:,.2f}")
            
            if pivot_data.pending_pivots:
                self.log_message("\nDanh sách pivot đang chờ xác nhận:")
                for pivot in pivot_data.pending_pivots:
                    self.log_message(f"\nThời gian: {pivot['time']}")
                    self.log_message(f"Loại: {pivot['type']}")
                    self.log_message(f"Giá ban đầu: ${pivot['price']:,.2f}")
                    self.log_message(f"Xác nhận: {pivot['confirmation_candles']}/3")
                    if pivot['type'] in ["H", "HH", "LH"]:
                        self.log_message(f"Giá cao nhất: ${pivot['highest_price']:,.2f}")
                        self.log_message(f"Thời gian cao nhất: {pivot['highest_time']}")
                        self.log_message(f"Số nến thấp hơn: {pivot['lower_prices']}")
                    else:
                        self.log_message(f"Giá thấp nhất: ${pivot['lowest_price']:,.2f}")
                        self.log_message(f"Thời gian thấp nhất: {pivot['lowest_time']}")
                        self.log_message(f"Số nến cao hơn: {pivot['higher_prices']}")
            
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
