from binance.client import Client
from datetime import datetime, timedelta
import re
import os
import traceback 
import sys
import pandas as pd
import pytz
from pathlib import Path
from s1 import pivot_data, detect_pivot, save_log, set_current_time_and_user

DEBUG_LOG_FILE = "debug_historical_test.log"

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
 
    def validate_data(self, df):
        """Kiểm tra dữ liệu trước khi xử lý"""
        if df.empty:
            raise ValueError("Không có dữ liệu")
            
        required_columns = ['datetime', 'time', 'high', 'low', 'price']
        missing_columns = [col for col in required_columns if col not in df.columns]
        if missing_columns:
            raise ValueError(f"Thiếu các cột: {missing_columns}")
            
        # Kiểm tra giá trị hợp lệ
        if df['high'].min() <= 0 or df['low'].min() <= 0:
            raise ValueError("Phát hiện giá không hợp lệ (<=0)")
            
        # Kiểm tra high >= low
        if not (df['high'] >= df['low']).all():
            raise ValueError("Phát hiện high < low")
    
    def analyze_results(self, final_pivots, df):
        """Phân tích kết quả test chi tiết"""
        self.log_message("\n=== Phân tích kết quả ===", "SUMMARY")
        
        # Thống kê pivot
        pivot_types = {}
        for pivot in final_pivots:
            pivot_type = pivot['type']
            pivot_types[pivot_type] = pivot_types.get(pivot_type, 0) + 1
        
        # Log thống kê
        self.log_message(f"Tổng số nến: {len(df)}")
        self.log_message(f"Tổng số pivot: {len(final_pivots)}")
        
        # Chi tiết từng loại pivot
        for ptype in ['HH', 'HL', 'LH', 'LL']:
            count = pivot_types.get(ptype, 0)
            self.log_message(f"- {ptype}: {count}")
        
        # Thêm thống kê thời gian
        if final_pivots:
            time_diffs = []
            for i in range(1, len(final_pivots)):
                current = datetime.strptime(final_pivots[i]['time'], '%H:%M')
                previous = datetime.strptime(final_pivots[i-1]['time'], '%H:%M')
                diff = (current - previous).total_seconds() / 60  # Convert to minutes
                time_diffs.append(diff)
                
            if time_diffs:
                avg_time = sum(time_diffs) / len(time_diffs)
                self.log_message(f"\nThời gian trung bình giữa các pivot: {avg_time:.1f} phút")
    
    def save_test_results(self, df, results):
        """
        Lưu kết quả test vào Excel và vẽ biểu đồ
        
        Parameters:
        df (DataFrame): DataFrame chứa dữ liệu gốc với các cột datetime, time, high, low, price
        results (list): Danh sách các pivot đã được xác nhận
        """
        try:
            # Lấy danh sách pivot từ pivot_data
            confirmed_pivots = pivot_data.confirmed_pivots.copy()
            
            # Tạo DataFrame mới cho các pivot
            pivot_records = []
            
            for pivot in confirmed_pivots:
                # Tìm datetime tương ứng từ DataFrame gốc
                matching_time = df[df['time'] == pivot['time']]
                if not matching_time.empty:
                    pivot_datetime = matching_time['datetime'].iloc[0]
                else:
                    # Nếu không tìm thấy trong df, sử dụng datetime từ pivot
                    pivot_datetime = pivot.get('datetime', None)
                
                if pivot_datetime:
                    pivot_records.append({
                        'datetime': pivot_datetime,
                        'price': pivot['price'],
                        'pivot_type': pivot['type']
                    })
            
            # Chuyển list thành DataFrame và sắp xếp theo thời gian
            pivot_df = pd.DataFrame(pivot_records)
            if not pivot_df.empty:
                pivot_df = pivot_df.sort_values('datetime')
            
            # Tạo Excel file với xlsxwriter
            with pd.ExcelWriter('test_results.xlsx', engine='xlsxwriter') as writer:
                # Ghi vào sheet Pivot Analysis
                pivot_df.to_excel(writer, sheet_name='Pivot Analysis', index=False)
                
                workbook = writer.book
                worksheet = writer.sheets['Pivot Analysis']
                
                # Định dạng cột
                date_format = workbook.add_format({
                    'num_format': 'yyyy-mm-dd hh:mm:ss',
                    'align': 'center'
                })
                price_format = workbook.add_format({
                    'num_format': '$#,##0.00',
                    'align': 'right'
                })
                header_format = workbook.add_format({
                    'bold': True,
                    'align': 'center',
                    'bg_color': '#D9D9D9'
                })
                
                # Áp dụng định dạng cho header
                for col_num, value in enumerate(['Datetime', 'Price', 'Pivot Type']):
                    worksheet.write(0, col_num, value, header_format)
                
                # Định dạng các cột
                worksheet.set_column('A:A', 20, date_format)    # datetime
                worksheet.set_column('B:B', 15, price_format)   # price
                worksheet.set_column('C:C', 12)                 # pivot_type
                
                # Thêm thống kê
                stats_row = len(pivot_df) + 3
                stats_format = workbook.add_format({
                    'bold': True,
                    'bg_color': '#E6E6E6'
                })
                
                # Viết phần thống kê
                worksheet.write(stats_row, 0, "Thống kê:", stats_format)
                worksheet.write(stats_row + 1, 0, "Tổng số pivot:")
                worksheet.write(stats_row + 1, 1, len(pivot_df), price_format)
                
                # Thống kê theo loại pivot
                pivot_counts = pivot_df['pivot_type'].value_counts() if not pivot_df.empty else pd.Series()
                worksheet.write(stats_row + 2, 0, "Phân bố pivot:", stats_format)
                
                row = stats_row + 3
                for pivot_type in ['HH', 'HL', 'LH', 'LL']:
                    count = pivot_counts.get(pivot_type, 0)
                    worksheet.write(row, 0, f"{pivot_type}:")
                    worksheet.write(row, 1, count)
                    row += 1
                
                # Tạo biểu đồ
                chart = workbook.add_chart({'type': 'scatter'})
                
                if not pivot_df.empty:
                    # Thêm series cho price
                    chart.add_series({
                        'name': 'Pivot Points',
                        'categories': f"='Pivot Analysis'!$A$2:$A${len(pivot_df) + 1}",  # Thêm dấu nháy đơn
                        'values': f"='Pivot Analysis'!$B$2:$B${len(pivot_df) + 1}",      # Thêm dấu nháy đơn
                        'marker': {
                            'type': 'circle',
                            'size': 8,
                            'fill': {'color': '#FF4B4B'},
                            'border': {'color': '#FF4B4B'}
                        },
                        'line': {'none': True}
                    })
                
                # Định dạng biểu đồ
                chart.set_title({
                    'name': 'Pivot Points Analysis',
                    'name_font': {'size': 14, 'bold': True}
                })
                
                chart.set_x_axis({
                    'name': 'Time',
                    'num_format': 'dd/mm/yyyy\nhh:mm',
                    'label_position': 'low',
                    'major_unit': 1,
                    'major_unit_type': 'days',
                    'line': {'color': '#CCCCCC'},
                    'major_gridlines': {'visible': True, 'line': {'color': '#CCCCCC'}}
                })
                
                chart.set_y_axis({
                    'name': 'Price',
                    'num_format': '$#,##0',
                    'line': {'color': '#CCCCCC'},
                    'major_gridlines': {'visible': True, 'line': {'color': '#CCCCCC'}}
                })
                
                chart.set_legend({'position': 'bottom'})
                chart.set_size({'width': 920, 'height': 600})
                
                # Chèn biểu đồ vào worksheet
                worksheet.insert_chart('E2', chart)
                
                # Thêm sheet Data để lưu dữ liệu gốc
                df_to_save = df[['datetime', 'time', 'high', 'low', 'price']].copy()
                df_to_save.to_excel(writer, sheet_name='Raw Data', index=False)
                
                # Định dạng sheet Data
                worksheet_data = writer.sheets['Raw Data']
                worksheet_data.set_column('A:A', 20, date_format)  # datetime
                worksheet_data.set_column('B:B', 10)               # time
                worksheet_data.set_column('C:E', 15, price_format) # high, low, price
                
                # Log kết quả
                self.log_message("\nĐã lưu kết quả test vào file test_results.xlsx", "SUCCESS")
                self.log_message(f"Tổng số pivot: {len(pivot_df)}", "INFO")
                self.log_message("Phân bố pivot:", "INFO")
                for pivot_type in ['HH', 'HL', 'LH', 'LL']:
                    count = pivot_counts.get(pivot_type, 0)
                    self.log_message(f"- {pivot_type}: {count}", "INFO")
                
                return True
                
        except Exception as e:
            self.log_message(f"Lỗi khi lưu Excel: {str(e)}", "ERROR")
            self.log_message(traceback.format_exc(), "ERROR")
            return False

    def run_test(self):
        """Chạy historical test cho S1"""
        try:
            # Thời gian bắt đầu: 00:00 15/03 VN = 17:00 14/03 UTC
            start_time = datetime(2025, 3, 14, 17, 0, 0)
            start_time_vn = (start_time + timedelta(hours=7)).strftime('%Y-%m-%d %H:%M:%S')
            
            # Thời gian kết thúc: 19:00 15/03 VN = 12:00 15/03 UTC
            end_time = datetime(2025, 3, 15, 12, 0, 0)  
            end_time_vn = (end_time + timedelta(hours=7)).strftime('%Y-%m-%d %H:%M:%S')
                
            self.log_message("\n=== Bắt đầu test S1 ===", "INFO")
            self.log_message(f"Symbol: {self.symbol}", "INFO")
            self.log_message(f"Interval: {self.interval}", "INFO")
            self.log_message(f"User: {self.user_login}", "INFO")
            self.log_message(f"Thời gian bắt đầu (Vietnam): {start_time_vn}", "INFO")
            self.log_message(f"Thời gian kết thúc (Vietnam): {end_time_vn}", "INFO")
            self.log_message(f"Thời gian bắt đầu (UTC): {start_time.strftime('%Y-%m-%d %H:%M:%S')}", "INFO")
            self.log_message(f"Thời gian kết thúc (UTC): {end_time.strftime('%Y-%m-%d %H:%M:%S')}", "INFO")
                
            # Lấy dữ liệu từ Binance
            klines = self.client.get_historical_klines(
                self.symbol,
                Client.KLINE_INTERVAL_30MINUTE,
                start_str=int(start_time.timestamp() * 1000),
                end_str=int(end_time.timestamp() * 1000)
            )
                
            if not klines:
                self.log_message("Không tìm thấy dữ liệu cho khoảng thời gian này", "ERROR")
                return None

            # Chuyển đổi dữ liệu thành DataFrame
            df = pd.DataFrame(klines, columns=[
                'timestamp', 'open', 'high', 'low', 'close', 
                'volume', 'close_time', 'quote_volume', 'trades',
                'buy_base_volume', 'buy_quote_volume', 'ignore'
            ])

            # Xử lý timestamp và timezone
            df['datetime'] = pd.to_datetime(df['timestamp'], unit='ms', utc=True)
            vietnam_tz = pytz.timezone('Asia/Ho_Chi_Minh')
            df['datetime'] = df['datetime'].dt.tz_convert(vietnam_tz)
            df['datetime'] = df['datetime'].dt.tz_localize(None)
            df['time'] = df['datetime'].dt.strftime('%H:%M')

            # Chọn và format dữ liệu cần thiết
            df = df[['datetime', 'time', 'high', 'low', 'close']]
            df = df.rename(columns={'close': 'price'})
            for col in ['high', 'low', 'price']:
                df[col] = df[col].astype(float)
                
            self.log_message(f"\nTổng số nến: {len(df)}", "INFO")
                
            # Reset S1
            pivot_data.clear_all()
                
            # Thêm pivot ban đầu
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
                
            # Thêm pivot ban đầu vào S1
            for pivot in initial_pivots:
                pivot_data.confirmed_pivots.append(pivot)
                    
            self.log_message("\nĐã thêm pivot ban đầu:", "INFO")
            for pivot in initial_pivots:
                self.log_message(f"- {pivot['type']} tại ${pivot['price']:,.2f} ({pivot['time']})", "INFO")

            # Cung cấp dữ liệu cho S1
            self.log_message("\nBắt đầu cung cấp dữ liệu cho S1...", "INFO")

            # Thêm biến để theo dõi thời điểm log cuối
            last_log_time = None
            log_interval = timedelta(minutes=30)  # Log mỗi 30 phút
            
            for index, row in df.iterrows():
                current_time = row['datetime']
                
                # Chỉ log nếu đã đủ interval hoặc có biến động lớn
                significant_change = abs(row['high'] - row['low']) > 100  # Biến động >$100
                should_log = (
                    last_log_time is None or 
                    (current_time - last_log_time) >= log_interval or
                    significant_change
                )
                
                if should_log:
                    self.log_message(f"\n=== Nến {row['time']} ===", "DETAIL")
                    self.log_message(f"Giá: ${row['price']:,.2f}")
                    if significant_change:
                        self.log_message(f"⚠️ Biến động lớn: ${row['high']:,.2f} - ${row['low']:,.2f}")
                    last_log_time = current_time
                
                # Cung cấp dữ liệu cho S1
                price_data = {
                    'time': row['time'],
                    'price': row['price'],
                    'high': row['high'],
                    'low': row['low']
                }
                pivot_data.add_price_data(price_data)
                
            # Lấy kết quả từ S1
            final_pivots = pivot_data.confirmed_pivots.copy()
                
            # Log kết quả cuối cùng
            self.log_message("\n=== Kết quả test S1 ===", "SUMMARY")
            self.log_message(f"Tổng số nến đã xử lý: {len(df)}")
            self.log_message(f"Tổng số pivot được S1 xác nhận: {len(final_pivots)}")
                
            if final_pivots:
                self.log_message("\nDanh sách pivot S1 đã xác nhận:")
                for pivot in final_pivots:
                    self.log_message(f"- {pivot['type']} tại ${pivot['price']:,.2f} ({pivot['time']})")
                
            # Lưu kết quả vào Excel
            self.save_test_results(df, final_pivots)
                
            return final_pivots
                
        except Exception as e:
            self.log_message(f"❌ Lỗi khi chạy test: {str(e)}", "ERROR")
            self.log_message(traceback.format_exc(), "ERROR")
            return None
            
def main():
    try:
        # Set thời gian hiện tại UTC
        utc_time = "2025-03-20 09:26:57"  # Thời gian mới
        
        # Chuyển sang múi giờ Việt Nam (+7)
        utc = pytz.UTC
        vietnam_tz = pytz.timezone('Asia/Ho_Chi_Minh')
        utc_dt = datetime.strptime(utc_time, '%Y-%m-%d %H:%M:%S').replace(tzinfo=utc)
        vietnam_time = utc_dt.astimezone(vietnam_tz)
        
        # Format thời gian VN
        current_time = vietnam_time.strftime('%Y-%m-%d %H:%M:%S')
        save_log(f"\n=== Thông tin thời gian ===", DEBUG_LOG_FILE)
        save_log(f"UTC time: {utc_time}", DEBUG_LOG_FILE)
        save_log(f"Vietnam time: {current_time} (GMT+7)", DEBUG_LOG_FILE)
        
        current_user = "lenhat20791"
        
        print(f"Current Date and Time (UTC): {utc_time}")
        print(f"Current User's Login: {current_user}")
        
        # Cung cấp thông tin môi trường cho S1
        set_current_time_and_user(current_time, current_user)
        
        # Chạy test
        tester = S1HistoricalTester(current_user)
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
