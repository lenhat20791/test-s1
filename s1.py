import logging
import json
import os
import time
from datetime import datetime, timedelta
from telegram import Update, Bot
from telegram.ext import Updater, CommandHandler, CallbackContext, JobQueue
from binance.client import Client
from openpyxl import Workbook
from openpyxl.chart import LineChart, Reference, Series
from openpyxl.chart.axis import DateAxis
from openpyxl.styles import Font, PatternFill, Alignment
from openpyxl.utils import get_column_letter

# Configurations
TOKEN = "7637023247:AAG_utVTC0rXyfute9xsBdh-IrTUE3432o8"
BINANCE_API_KEY = "aVim4czsoOzuLxk0CsEsV0JwE58OX90GRD8OvDfT8xH2nfSEC0mMnMCVrwgFcSEi"
BINANCE_API_SECRET = "rIQ2LLUtYWBcXt5FiMIHuXeeDJqeREbvw8r9NlTJ83gveSAvpSMqd1NBoQjAodC4"
CHAT_ID = 7662080576
LOG_FILE = "bot_log.json"
PATTERN_LOG_FILE = "pattern_log.txt"
DEBUG_LOG_FILE = "debug_log.txt"
EXCEL_FILE = "pivots.xlsx"

# Setup Logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Ensure log files exist
for file in [LOG_FILE, PATTERN_LOG_FILE, DEBUG_LOG_FILE]:
    if not os.path.exists(file):
        with open(file, "w", encoding="utf-8") as f:
            f.write("=== Log Initialized ===\n")


# Store pivot data
detected_pivots = []  # Stores last 15 pivots
user_provided_pivots = []  # Stores pivots provided via /moc command

# Initialize Binance Client
binance_client = Client(BINANCE_API_KEY, BINANCE_API_SECRET)

class PivotData:
    def __init__(self):
        self.detected_pivots = []  # Lưu các pivot tự động phát hiện (tối đa 15)
        self.user_provided_pivots = []  # Lưu các pivot từ người dùng qua lệnh /moc
        self.MIN_PRICE_CHANGE = 0.005  # 0.5% thay đổi giá tối thiểu
        self.MIN_PIVOT_DISTANCE = 3  # Khoảng cách tối thiểu giữa các pivot (số nến)
        self.TREND_WINDOW = 10  # Số nến để xác định xu hướng
        self.MAX_PIVOTS = 15  # Số lượng pivot tối đa lưu trữ
        self.last_sync_time = datetime.now()

    def add_user_pivot(self, pivot_type: str, price: float, time: str) -> bool:
        """Thêm pivot từ lệnh /moc của user"""
        try:
            new_pivot = {
                "type": pivot_type.upper(),
                "price": price,
                "time": time,
                "source": "user"
            }
            self.user_provided_pivots.append(new_pivot)
            
            # Giới hạn số lượng pivot
            if len(self.user_provided_pivots) > self.MAX_PIVOTS:
                self.user_provided_pivots.pop(0)
            
            save_log(f"User pivot added: {pivot_type} at {time} price: ${price}", DEBUG_LOG_FILE)
            return True
        except Exception as e:
            save_log(f"Error adding user pivot: {str(e)}", DEBUG_LOG_FILE)
            return False

    def add_detected_pivot(self, price: float, price_type: str) -> bool:
        """Thêm pivot từ hệ thống tự động phát hiện"""
        try:
            # Kiểm tra điều kiện thêm pivot
            if not self._can_add_pivot(price):
                return False

            # Xác định loại pivot
            pivot_type = self._determine_pivot_type(price, price_type)
            if not pivot_type:
                return False

            # Tạo pivot mới
            new_pivot = {
                "type": pivot_type,
                "price": price,
                "time": datetime.now().strftime("%H:%M"),
                "source": "system"
            }
            self.detected_pivots.append(new_pivot)

            # Giới hạn số lượng pivot
            if len(self.detected_pivots) > self.MAX_PIVOTS:
                self.detected_pivots.pop(0)

            save_log(f"Detected pivot: {pivot_type} at {new_pivot['time']} price: ${price}", DEBUG_LOG_FILE)
            return True
        except Exception as e:
            save_log(f"Error adding detected pivot: {str(e)}", DEBUG_LOG_FILE)
            return False

    def _can_add_pivot(self, price: float) -> bool:
        """Kiểm tra các điều kiện để thêm pivot mới"""
        combined_pivots = self.get_all_pivots()
        if not combined_pivots:
            return True

        # Kiểm tra khoảng cách thời gian
        last_pivot = combined_pivots[-1]
        last_time = datetime.strptime(last_pivot["time"], "%H:%M")
        current_time = datetime.now()
        time_diff = (current_time - last_time).total_seconds() / 300  # Đổi sang số nến 5m
        
        if time_diff < self.MIN_PIVOT_DISTANCE:
            save_log(f"Pivot too close in time: {time_diff} candles", DEBUG_LOG_FILE)
            return False

        # Kiểm tra biến động giá
        price_change = abs(price - last_pivot["price"]) / last_pivot["price"]
        if price_change < self.MIN_PRICE_CHANGE:
            save_log(f"Price change too small: {price_change:.2%}", DEBUG_LOG_FILE)
            return False

        return True

    def get_all_pivots(self) -> list:
        """Lấy tất cả pivot đã sắp xếp theo thời gian"""
        all_pivots = self.user_provided_pivots + self.detected_pivots
        all_pivots.sort(key=lambda x: datetime.strptime(x["time"], "%H:%M"))
        return all_pivots

    def clear_all(self):
        """Xóa tất cả pivot points"""
        self.detected_pivots.clear()
        self.user_provided_pivots.clear()
        save_log("All pivot points cleared", DEBUG_LOG_FILE)

    def get_recent_pivots(self, count: int = 5) -> list:
        """Lấy số lượng pivot gần nhất"""
        all_pivots = self.get_all_pivots()
        return all_pivots[-count:] if all_pivots else []

    def check_pattern(self) -> tuple[bool, str]:
        """Kiểm tra mẫu hình và trả về (có_mẫu_hình, tên_mẫu_hình)"""
        patterns = {
            "bullish_reversal": [
                ["HH", "HL", "HH", "HL", "HH"],
                ["LH", "HL", "HH", "HL", "HH"],
                ["HH", "HH", "HH"],
                ["HH", "HL", "HH", "HH"]
            ],
            "bearish_reversal": [
                ["LL", "LL", "LH", "LL"],
                ["LL", "LH", "LL", "LH", "LL"],
                ["LL", "LL", "LL"],
                ["LL", "LH", "LL", "LH", "LL"],
                ["LL", "LH", "LL"]
            ]
        }

        last_pivots = [p["type"] for p in self.get_all_pivots()]
        for pattern_name, sequences in patterns.items():
            for sequence in sequences:
                if len(last_pivots) >= len(sequence):
                    if last_pivots[-len(sequence):] == sequence:
                        save_log(f"Pattern found: {pattern_name} ({','.join(sequence)})", PATTERN_LOG_FILE)
                        return True, pattern_name
        return False, ""

def save_log(log_message, filename):
    """ Save log messages to a text file """
    with open(filename, "a", encoding="utf-8") as f:
        f.write(f"{datetime.now().strftime('%Y-%m-%d %H:%M:%S')} [INFO] - {log_message}\n")

def save_to_excel():
    """ 
    Lưu dữ liệu pivot vào file Excel với các cải tiến:
    - Phân biệt pivot từ user và hệ thống
    - Thêm biểu đồ candlestick
    - Cải thiện định dạng và bố cục
    """
    try:
        all_pivots = pivot_data.get_all_pivots()
        if not all_pivots:
            save_log("No pivot data to save", DEBUG_LOG_FILE)
            return
        
        wb = Workbook()
        # Tạo worksheet cho pivot points
        ws_pivot = wb.active
        ws_pivot.title = "Pivot Points"
        
        # Định dạng tiêu đề
        headers = ["Time", "Type", "Price", "Source", "Change %", "Trend"]
        for col, header in enumerate(headers, 1):
            cell = ws_pivot.cell(row=1, column=col)
            cell.value = header
            cell.font = Font(bold=True)
            cell.fill = PatternFill(start_color="CCCCCC", end_color="CCCCCC", fill_type="solid")
            cell.alignment = Alignment(horizontal="center")
            ws_pivot.column_dimensions[get_column_letter(col)].width = 15

        # Thêm dữ liệu với định dạng màu và tính toán bổ sung
        prev_price = None
        trend = "N/A"
        
        for idx, pivot in enumerate(all_pivots, 2):
            # Thêm thông tin cơ bản
            ws_pivot.cell(row=idx, column=1, value=pivot["time"])
            ws_pivot.cell(row=idx, column=2, value=pivot["type"])
            ws_pivot.cell(row=idx, column=3, value=pivot["price"])
            ws_pivot.cell(row=idx, column=4, value=pivot["source"])
            
            # Tính % thay đổi và xu hướng
            if prev_price:
                change = ((pivot["price"] - prev_price) / prev_price) * 100
                ws_pivot.cell(row=idx, column=5, value=f"{change:+.2f}%")
                
                # Xác định xu hướng
                if change > 0:
                    trend = "↗ Tăng"
                    cell_color = "00FF00"  # Màu xanh lá
                elif change < 0:
                    trend = "↘ Giảm"
                    cell_color = "FF0000"  # Màu đỏ
                else:
                    trend = "→ Đi ngang"
                    cell_color = "FFFF00"  # Màu vàng
                
                # Thêm xu hướng và định dạng màu
                trend_cell = ws_pivot.cell(row=idx, column=6, value=trend)
                trend_cell.fill = PatternFill(start_color=cell_color, end_color=cell_color, fill_type="solid")
                
            prev_price = pivot["price"]
            
            # Định dạng các ô
            for col in range(1, 7):
                cell = ws_pivot.cell(row=idx, column=col)
                cell.alignment = Alignment(horizontal="center")
                
                # Thêm màu nền cho các pivot từ user
                if pivot["source"] == "user":
                    cell.fill = PatternFill(start_color="E6E6FA", end_color="E6E6FA", fill_type="solid")

        # Tạo biểu đồ
        chart = LineChart()
        chart.title = "Pivot Points Analysis"
        chart.style = 13
        chart.height = 15
        chart.width = 30
        
        # Dữ liệu cho biểu đồ
        data = Reference(ws_pivot, min_col=3, min_row=1, max_row=len(all_pivots) + 1)
        categories = Reference(ws_pivot, min_col=1, min_row=2, max_row=len(all_pivots) + 1)
        
        # Thêm series và định dạng
        chart.add_data(data, titles_from_data=True)
        chart.set_categories(categories)
        
        # Định dạng trục
        chart.x_axis.title = "Time"
        chart.y_axis.title = "Price (USD)"
        chart.x_axis.tickLblSkip = 2
        
        # Thêm các điểm đánh dấu
        series = chart.series[0]
        series.marker.symbol = "circle"
        series.marker.size = 8
        
        # Thêm biểu đồ vào worksheet
        ws_pivot.add_chart(chart, "H2")
        
        # Thêm thông tin tổng hợp
        summary_row = len(all_pivots) + 4
        ws_pivot.cell(row=summary_row, column=1, value="Thống kê:")
        ws_pivot.cell(row=summary_row + 1, column=1, value="Tổng số pivot:")
        ws_pivot.cell(row=summary_row + 1, column=2, value=len(all_pivots))
        ws_pivot.cell(row=summary_row + 2, column=1, value="Pivot từ user:")
        ws_pivot.cell(row=summary_row + 2, column=2, value=len([p for p in all_pivots if p["source"] == "user"]))
        ws_pivot.cell(row=summary_row + 3, column=1, value="Pivot từ hệ thống:")
        ws_pivot.cell(row=summary_row + 3, column=2, value=len([p for p in all_pivots if p["source"] == "system"]))
        
        # Lưu file
        wb.save(EXCEL_FILE)
        save_log(f"Pivot data saved to Excel with {len(all_pivots)} points", DEBUG_LOG_FILE)
        
    except Exception as e:
        error_msg = f"Error saving Excel file: {str(e)}"
        save_log(error_msg, DEBUG_LOG_FILE)
        logger.error(error_msg)
    
def get_binance_price(context: CallbackContext):
    """ Fetches high and low prices for the last 5-minute candlestick """
    try:
        klines = binance_client.futures_klines(symbol="BTCUSDT", interval="5m", limit=2)
        last_candle = klines[-2]  # Ensure we get the closed candle
        high_price = float(last_candle[2])
        low_price = float(last_candle[3])
        
        save_log(f"Thu thập dữ liệu nến 5m: Cao nhất = {high_price}, Thấp nhất = {low_price}", DEBUG_LOG_FILE)
        
        detect_pivot(high_price, "H")
        detect_pivot(low_price, "L")
        save_to_excel()
    except Exception as e:
        logger.error(f"Binance API Error: {e}")
        save_log(f"Binance API Error: {e}", DEBUG_LOG_FILE)
        
def schedule_next_run(job_queue):
    """ Schedule the next run of get_binance_price exactly at the next 5-minute mark """
    now = datetime.now()
    next_run = now.replace(second=0, microsecond=0) + timedelta(minutes=(5 - now.minute % 5))
    delay = (next_run - now).total_seconds()
    
    save_log(f"Lên lịch chạy vào {next_run.strftime('%Y-%m-%d %H:%M:%S')}", DEBUG_LOG_FILE)
    job_queue.run_once(get_binance_price, delay)
    job_queue.run_repeating(get_binance_price, interval=300, first=delay)

def detect_pivot(price, price_type):
    """ 
    Xác định pivot points với các cải tiến:
    - Phân tích xu hướng tổng thể
    - Lọc nhiễu
    - Xác định điểm pivot chính xác hơn
    - Lưu trữ pivot data cấu trúc
    """
    try:
        # Phân tích xu hướng
        trend = _analyze_trend(pivot_data.get_all_pivots())
        save_log(f"Xu hướng hiện tại: {'Tăng' if trend > 0 else 'Giảm' if trend < 0 else 'Đi ngang'}", DEBUG_LOG_FILE)

        # Thêm pivot mới
        if pivot_data.add_detected_pivot(price, price_type):
            save_log(f"Đã thêm pivot mới: {price_type} - Giá: ${price:,.2f}", DEBUG_LOG_FILE)
            
            # Kiểm tra và lưu vào Excel
            save_to_excel()
            
            # Kiểm tra mẫu hình
            has_pattern, pattern_name = pivot_data.check_pattern()
            if has_pattern:
                # Tạo thông báo chi tiết
                recent_pivots = pivot_data.get_recent_pivots(5)  # Lấy 5 pivot gần nhất
                message = _create_alert_message(pattern_name, price, recent_pivots)
                send_alert(message)
                
    except Exception as e:
        error_msg = f"Lỗi trong quá trình phát hiện pivot: {str(e)}"
        save_log(error_msg, DEBUG_LOG_FILE)
        logger.error(error_msg)

def _analyze_trend(pivots, window=10):
    """Phân tích xu hướng dựa trên các pivot gần đây"""
    if len(pivots) < window:
        return 0
    
    recent_pivots = pivots[-window:]
    prices = [p["price"] for p in recent_pivots]
    price_changes = [prices[i] - prices[i-1] for i in range(1, len(prices))]
    
    # Tính toán xu hướng
    up_moves = sum(1 for x in price_changes if x > 0)
    down_moves = sum(1 for x in price_changes if x < 0)
    
    # Tính % thay đổi tổng thể
    total_change = (prices[-1] - prices[0]) / prices[0] * 100
    
    # Kết hợp số lượng move và % thay đổi để xác định xu hướng
    if up_moves > down_moves and total_change > 1:  # Tăng rõ ràng
        return 2
    elif up_moves > down_moves:  # Tăng nhẹ
        return 1
    elif down_moves > up_moves and total_change < -1:  # Giảm rõ ràng
        return -2
    elif down_moves > up_moves:  # Giảm nhẹ
        return -1
    return 0  # Đi ngang

def _create_alert_message(pattern_name, current_price, recent_pivots):
    """Tạo thông báo chi tiết khi phát hiện mẫu hình"""
    vietnam_time = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    
    # Xác định loại mẫu hình và biểu tượng
    if "bullish" in pattern_name.lower():
        pattern_symbol = "🟢"
        direction = "tăng"
    else:
        pattern_symbol = "🔴"
        direction = "giảm"
        
    message = (
        f"{pattern_symbol} CẢNH BÁO MẪU HÌNH {direction.upper()} - {vietnam_time}\n\n"
        f"Giá hiện tại: ${current_price:,.2f}\n"
        f"Mẫu hình: {pattern_name}\n\n"
        f"5 pivot gần nhất:\n"
    )
    
    # Thêm thông tin về 5 pivot gần nhất
    for i, pivot in enumerate(recent_pivots[::-1], 1):
        message += f"{i}. {pivot['type']}: ${pivot['price']:,.2f} ({pivot['time']})\n"
        
    return message

def send_alert(message):
    """Gửi cảnh báo qua Telegram với thông tin chi tiết"""
    try:
        bot = Bot(token=TOKEN)
        bot.send_message(
            chat_id=CHAT_ID,
            text=message,
            parse_mode='HTML'
        )
        save_log("Đã gửi cảnh báo mẫu hình", DEBUG_LOG_FILE)
    except Exception as e:
        save_log(f"Lỗi gửi cảnh báo: {str(e)}", DEBUG_LOG_FILE)

def determine_initial_pivot_type(price, price_type, pivots):
    """Xác định loại pivot khi có ít dữ liệu"""
    if not pivots:
        return "HH" if price_type == "H" else "LL"
    
    last_pivot = pivots[-1]
    if price_type == "H":
        return "HH" if price > last_pivot["price"] else "LH"
    else:
        return "LL" if price < last_pivot["price"] else "HL"

def determine_pivot_type(price, price_type, pivots, trend):
    """Xác định loại pivot dựa trên xu hướng và cấu trúc giá"""
    last_5_pivots = [p["price"] for p in pivots[-5:]]
    a, b, c, d, e = last_5_pivots
    
    if price_type == "H":
        if trend > 0:  # Xu hướng tăng
            if price > max(last_5_pivots):
                return "HH"
            elif c > b and c > d and price > c:
                return "HH"
            else:
                return "LH"
        else:  # Xu hướng giảm
            if price < min(last_5_pivots):
                return "LH"
            else:
                return verify_lower_high(price, last_5_pivots)
    else:  # price_type == "L"
        if trend < 0:  # Xu hướng giảm
            if price < min(last_5_pivots):
                return "LL"
            elif c < b and c < d and price < c:
                return "LL"
            else:
                return "HL"
        else:  # Xu hướng tăng
            if price > max(last_5_pivots):
                return "HL"
            else:
                return verify_higher_low(price, last_5_pivots)

def verify_lower_high(price, prices):
    """Xác minh điểm LH"""
    avg_high = sum(p for p in prices if p > price) / len([p for p in prices if p > price])
    return "LH" if price < avg_high else None

def verify_higher_low(price, prices):
    """Xác minh điểm HL"""
    avg_low = sum(p for p in prices if p < price) / len([p for p in prices if p < price])
    return "HL" if price > avg_low else None
   
def check_pattern():
    """ Checks if detected pivots match predefined patterns."""
    patterns = {
        "bullish_reversal": [
            "HH", "HL", "HH", "HL", "HH",
            "LH", "HL", "HH", "HL", "HH",
            "HH", "HH", "HH",
            "HH", "HL", "HH", "HH"
        ],
        "bearish_reversal": [
            "LL", "LL", "LH", "LL",
            "LL", "LH", "LL", "LH", "LL",
            "LL", "LL", "LL",
            "LL", "LH", "LL", "LH", "LL",
            "LL", "LH", "LL"
        ]
    }
    
    last_pivots = [p["type"] for p in detected_pivots]
    for pattern_name, sequence in patterns.items():
        if last_pivots[-len(sequence):] == sequence:
            save_log(f"Xác định mẫu hình: {pattern_name} ({', '.join(sequence)})", PATTERN_LOG_FILE)
            return True
    return False

def send_alert():
    """ Sends an alert message to Telegram."""
    bot = Bot(token=TOKEN)
    bot.send_message(chat_id=CHAT_ID, text="⚠️ Pattern Detected! Check the market.")

def moc(update: Update, context: CallbackContext):
    """ Handles the /moc command to receive multiple pivot points and resets logic."""
    global user_provided_pivots, detected_pivots
    args = context.args
    
    logger.info(f"Received /moc command with args: {args}")
    save_log(f"Received /moc command with args: {args}", DEBUG_LOG_FILE)
    
    if len(args) < 4 or (len(args) - 1) % 3 != 0:
        update.message.reply_text("⚠️ Sai định dạng! Dùng: /moc btc lh 82000 14h20 hl 81000 14h30 hh 83000 14h50")
        return
    
    asset = args[0].lower()
    if asset != "btc":
        update.message.reply_text("⚠️ Chỉ hỗ trợ BTC! Ví dụ: /moc btc lh 82000 14h20 hl 81000 14h30 hh 83000 14h50")
        return
        
    # **Xóa dữ liệu cũ** trước khi cập nhật mốc mới
    user_provided_pivots.clear()
    detected_pivots.clear()
    
    # Ghi nhận các mốc mới
    for i in range(1, len(args), 3):
        try:
            pivot_type = args[i]
            price = float(args[i + 1])
            time = args[i + 2]
            user_provided_pivots.append({"type": pivot_type, "price": price, "time": time})
            save_log(f"Nhận mốc {pivot_type} - Giá: {price} - Thời gian: {time}", DEBUG_LOG_FILE)
        except ValueError:
            update.message.reply_text(f"⚠️ Lỗi: Giá phải là số hợp lệ! ({args[i + 1]})")
            return
    
    # Giới hạn 15 mốc gần nhất
    if len(user_provided_pivots) > 15:
        user_provided_pivots = user_provided_pivots[-15:]

    # **Ghi đè dữ liệu vào pattern log**
    with open(PATTERN_LOG_FILE, "w", encoding="utf-8") as f:
        f.write("=== Pattern Log Reset ===\n")

    save_log(f"User Pivots Updated: {user_provided_pivots}", LOG_FILE)
    save_log(f"User Pivots Updated: {user_provided_pivots}", PATTERN_LOG_FILE)
    save_to_excel()

    # Phản hồi cho người dùng
    update.message.reply_text(f"✅ Đã nhận các mốc: {user_provided_pivots}")
    logger.info(f"User Pivots Updated: {user_provided_pivots}")

def main():
    """ Main entry point to start the bot."""
    updater = Updater(TOKEN, use_context=True)
    dp = updater.dispatcher
    job_queue = updater.job_queue
    
    dp.add_handler(CommandHandler("moc", moc))
    
    schedule_next_run(job_queue)  # Schedule the first execution at the next 5-minute mark
    
    print("Bot is running...")
    logger.info("Bot started successfully.")
    updater.start_polling()
    updater.idle()

if __name__ == "__main__":
    main()
