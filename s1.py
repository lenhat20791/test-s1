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

def save_log(log_message, filename):
    """ Save log messages to a text file """
    with open(filename, "a", encoding="utf-8") as f:
        f.write(f"{datetime.now().strftime('%Y-%m-%d %H:%M:%S')} [INFO] - {log_message}\n")

def save_to_excel():
    """ Saves pivot data to an Excel file with a chart."""
    try:
        if not detected_pivots:
            save_log("No pivot data to save", DEBUG_LOG_FILE)
            return
        
        wb = Workbook()
        ws = wb.active
        ws.title = "Pivot Points"
        
        # Định dạng tiêu đề
        headers = ["Time", "Type", "Price", "Change %"]
        for col, header in enumerate(headers, 1):
            cell = ws.cell(row=1, column=col)
            cell.value = header
            cell.font = Font(bold=True)
            cell.fill = PatternFill(start_color="CCCCCC", end_color="CCCCCC", fill_type="solid")
            cell.alignment = Alignment(horizontal="center")
            ws.column_dimensions[get_column_letter(col)].width = 15
        
        # Thêm dữ liệu với phần trăm thay đổi
        prev_price = None
        for idx, pivot in enumerate(detected_pivots, 2):
            ws.cell(row=idx, column=1, value=pivot["time"])
            ws.cell(row=idx, column=2, value=pivot["type"])
            ws.cell(row=idx, column=3, value=pivot["price"])
            
            # Tính % thay đổi
            if prev_price:
                change = ((pivot["price"] - prev_price) / prev_price) * 100
                ws.cell(row=idx, column=4, value=f"{change:+.2f}%")
            prev_price = pivot["price"]
            
            # Căn giữa các ô
            for col in range(1, 5):
                ws.cell(row=idx, column=col).alignment = Alignment(horizontal="center")
        
        # Tạo biểu đồ
        chart = LineChart()
        chart.title = "Pivot Points Analysis"
        chart.style = 13  # Chọn style đẹp cho biểu đồ
        
        # Dữ liệu cho biểu đồ
        data = Reference(ws, min_col=3, min_row=1, max_row=len(detected_pivots) + 1)
        categories = Reference(ws, min_col=1, min_row=2, max_row=len(detected_pivots) + 1)
        
        # Thêm series và đặt màu
        chart.add_data(data, titles_from_data=True)
        chart.set_categories(categories)
        
        # Định dạng trục
        chart.x_axis.title = "Time"
        chart.y_axis.title = "Price (USD)"
        chart.x_axis.tickLblSkip = 2
        
        # Thêm biểu đồ vào worksheet
        ws.add_chart(chart, "F2")
        
        # Lưu file - sử dụng biến toàn cục EXCEL_FILE
        wb.save(EXCEL_FILE)
        save_log(f"Pivot data saved to Excel with {len(detected_pivots)} points", DEBUG_LOG_FILE)
        
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
    """
    global detected_pivots, user_provided_pivots
    
    MIN_PRICE_CHANGE = 0.005  # 0.5% thay đổi giá tối thiểu
    MIN_PIVOT_DISTANCE = 3    # Khoảng cách tối thiểu giữa các pivot (theo số nến)
    TREND_WINDOW = 10         # Số nến để xác định xu hướng
    
    # Kết hợp pivots từ người dùng và tự động phát hiện
    combined_pivots = user_provided_pivots + detected_pivots
    
    # 1. Kiểm tra khoảng cách với pivot gần nhất
    if len(combined_pivots) > 0:
        last_pivot_time = datetime.strptime(combined_pivots[-1]["time"], "%H:%M")
        current_time = datetime.now()
        time_diff = (current_time - last_pivot_time).total_seconds() / 300  # Đổi sang số nến 5m
        if time_diff < MIN_PIVOT_DISTANCE:
            save_log(f"Bỏ qua pivot - quá gần pivot trước ({time_diff} nến)", DEBUG_LOG_FILE)
            return

    # 2. Lọc nhiễu dựa trên biên độ giá
    if len(combined_pivots) > 0:
        last_price = combined_pivots[-1]["price"]
        price_change = abs(price - last_price) / last_price
        if price_change < MIN_PRICE_CHANGE:
            save_log(f"Bỏ qua pivot - biến động giá quá nhỏ ({price_change:.2%})", DEBUG_LOG_FILE)
            return

    # 3. Xác định xu hướng tổng thể
    def calculate_trend(prices, window=TREND_WINDOW):
        if len(prices) < window:
            return 0
        
        recent_prices = prices[-window:]
        price_changes = [recent_prices[i] - recent_prices[i-1] for i in range(1, len(recent_prices))]
        trend = sum(1 for x in price_changes if x > 0) - sum(1 for x in price_changes if x < 0)
        return trend

    # 4. Xác định loại pivot dựa trên xu hướng và giá
    if len(combined_pivots) < 5:
        # Xử lý trường hợp ít dữ liệu
        pivot_type = determine_initial_pivot_type(price, price_type, combined_pivots)
    else:
        recent_prices = [p["price"] for p in combined_pivots[-TREND_WINDOW:]]
        trend = calculate_trend(recent_prices)
        pivot_type = determine_pivot_type(price, price_type, combined_pivots, trend)

    # 5. Thêm pivot mới nếu hợp lệ
    if pivot_type:
        new_pivot = {
            "type": pivot_type,
            "price": price,
            "time": datetime.now().strftime("%H:%M")
        }
        detected_pivots.append(new_pivot)
        
        # Giữ tối đa 15 pivot gần nhất
        if len(detected_pivots) > 15:
            detected_pivots.pop(0)
        
        save_log(f"Xác định {pivot_type} - Giá: {price}", PATTERN_LOG_FILE)
        save_to_excel()
        
        # Kiểm tra mẫu hình
        if check_pattern():
            send_alert()

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
