# main.py
# ESP32-S2 示波器，基于MicroPython
# 设计人：叶冀宇
# 更新时间：2025.6.03 23.09

import machine
import time
import st7789py
# 里面配置为资源模式。
# import vga1_8x16
# import vga1_16x32
# 上面这个字库不用了,用tft给的小字库，省点内存
import array
import math

# --- 接线 ---

# SPI总线
SPI_BUS = 1
SPI_BAUDRATE = 40000000  # 先跑40兆赫吧，80兆赫怕不稳
PIN_SPI_SCK = 35
PIN_SPI_MOSI = 36
PIN_TFT_CS = 37
PIN_TFT_DC = 38
PIN_TFT_RST = 39
# 这个屏的背光是直接点亮的，BLK就算了

# 分辨率
SCREEN_WIDTH = 320
SCREEN_HEIGHT = 240

# ADC
PIN_ADC_SIGNAL = 2
PIN_ADC_GAIN = 3

# 按键
PIN_BTN_1 = 15  # +
PIN_BTN_2 = 16  # -
PIN_BTN_3 = 17  # o

# --- 采样操作 ---
SAMPLE_COUNT = 1000 # 到头了
SAMPLE_RATE = 10000  # 10千赫到头了，不能再多了
SAMPLE_INTERVAL_US = 1000000 // SAMPLE_RATE

# 采样数组在此
# 无符号短整形，正好
samples = array.array('H', (0 for _ in range(SAMPLE_COUNT)))

# 全局变量
gain = 1.0
frequency = 0.0
zoom_factor = 0.3  # 初始缩放因数
current_theme_index = 0
last_btn_press_time = 50 # 按键消抖用的delay time

# --- UI ---

# 状态定义
STATE_MAIN = 0
STATE_THEME_SELECT = 1
current_state = STATE_MAIN

# 颜色主题定义
THEMES = [
    {"BG": st7789.BLACK, "WAVE": st7789.GREEN, "TEXT": st7789.WHITE, "UI_HIGHLIGHT": st7789.YELLOW},
    {"BG": st7789.WHITE, "WAVE": st7789.BLUE, "TEXT": st7789.BLACK, "UI_HIGHLIGHT": st7789.RED},
    {"BG": st7789.PURPLE, "WAVE": st7789.YELLOW, "TEXT": st7789.WHITE, "UI_HIGHLIGHT": st7789.CYAN},
    {"BG": st7789.rgb(20, 20, 40), "WAVE": st7789.CYAN, "TEXT": st7789.WHITE, "UI_HIGHLIGHT": st7789.MAGENTA},
]

# UI 布局
WAVEFORM_Y_START = 80
WAVEFORM_HEIGHT = 160
INFO_TEXT_Y = WAVEFORM_Y_START + WAVEFORM_HEIGHT + 10
MENU_Y = INFO_TEXT_Y + 20

# --- 初始化 ---

# ADC
adc_signal = machine.ADC(machine.Pin(PIN_ADC_SIGNAL))
adc_signal.atten(machine.ADC.ATTN_11DB)  # 这框架不让用12dB的衰减，救命
adc_signal.width(machine.ADC.WIDTH_12BIT) # 12-bit精度

adc_gain = machine.ADC(machine.Pin(PIN_ADC_GAIN))
adc_gain.atten(machine.ADC.ATTN_11DB)
adc_gain.width(machine.ADC.WIDTH_12BIT)

# 按键
btn1 = machine.Pin(PIN_BTN_1, machine.Pin.IN, machine.Pin.PULL_UP)
btn2 = machine.Pin(PIN_BTN_2, machine.Pin.IN, machine.Pin.PULL_UP)
btn3 = machine.Pin(PIN_BTN_3, machine.Pin.IN, machine.Pin.PULL_UP)

# TFT
spi = machine.SPI(SPI_BUS, baudrate=SPI_BAUDRATE, sck=machine.Pin(PIN_SPI_SCK), mosi=machine.Pin(PIN_SPI_MOSI))
tft = st7789.ST7789(
    spi, SCREEN_WIDTH, SCREEN_HEIGHT,
    cs=machine.Pin(PIN_TFT_CS),
    dc=machine.Pin(PIN_TFT_DC),
    rst=machine.Pin(PIN_TFT_RST) if PIN_TFT_RST != -1 else None,
)
tft.init()
# tft.inversion_mode(True) 
# 不用了，没事了

# --- 功能函数们 ---

def acquire_samples():
    global samples
    # 用ticks_us()和ticks_diff()给的软定时
    start_time = time.ticks_us()
    for i in range(SAMPLE_COUNT):
        target_time = time.ticks_add(start_time, i * SAMPLE_INTERVAL_US)
        # 想你了，vTaskDelay()
        while time.ticks_diff(target_time, time.ticks_us()) > 0:
            pass
        samples[i] = adc_signal.read()

def calculate_parameters():
    global gain, frequency

    # 计算增益
    in_val = adc_gain.read()
    gain = 10.0 * in_val / 4095.0 + 1.0

    # 计算频率
    # Python给的FFT太。。。垃圾了，手搓一个零点交越算法吧。
    crossover_count = 0
    for s in samples:
        if 2000 < s < 2080:
            crossover_count += 1
    
    # 公式是：Frequency = CrossoverCount * 5，实际上更合理的写法是根据宏定义的采样率写，但是我好懒
    frequency = float(crossover_count * 5)

def draw_waveform():
    theme = THEMES[current_theme_index]
    tft.fill_rect(0, WAVEFORM_Y_START, SCREEN_WIDTH, WAVEFORM_HEIGHT, theme["BG"])

    prev_x, prev_y = 0, 0
    
    # 挨个画点，说实话我很思念我的全屏缓冲区
    for i in range(1, SAMPLE_COUNT):
        # 重新算屏幕X坐标，考虑缩放
        x = int(i * zoom_factor)
        if x >= SCREEN_WIDTH:
            break

        # 屏幕Y坐标0在顶部，所以需要反转
        y = WAVEFORM_Y_START + WAVEFORM_HEIGHT - int(samples[i] * WAVEFORM_HEIGHT / 4095)
        
        tft.point(x, y, theme["WAVE"])

def draw_ui():
    theme = THEMES[current_theme_index]
    
    # 清屏
    tft.fill_rect(0, INFO_TEXT_Y, SCREEN_WIDTH, SCREEN_HEIGHT - INFO_TEXT_Y, theme["BG"])
    
    # 显示 Gain 和 Frequency
    info_text = f"Gain: {gain:.2f}  Freq: {frequency:.1f} Hz"
    tft.text(cl5x8, info_text, 5, INFO_TEXT_Y, theme["TEXT"], theme["BG"])
    
    # 根据当前状态显示菜单
    if current_state == STATE_MAIN:
        menu_items = ["Zoom+", "Zoom-", "Theme"]
    elif current_state == STATE_THEME_SELECT:
        menu_items = ["Former", "Next", "Back"]
    
    # 绘制菜单项
    item_width = SCREEN_WIDTH // 3
    for i, item in enumerate(menu_items):
        tft.text(cl5x8, item, i * item_width + 15, MENU_Y, theme["TEXT"], theme["BG"])
        
def handle_input():
    global current_state, current_theme_index, zoom_factor, last_btn_press_time
    
    # 按键消抖（青春版）
    debounce_delay = last_btn_press_time
    if time.ticks_diff(time.ticks_ms(), last_btn_press_time) < debounce_delay:
        return

    # 读取按键状态 
    btn1_pressed = btn1.value() == 0
    btn2_pressed = btn2.value() == 0
    btn3_pressed = btn3.value() == 0

    action_taken = False

    if current_state == STATE_MAIN:
        if btn1_pressed: # Zoom+
            zoom_factor *= 1.5
            action_taken = True
        elif btn2_pressed: # Zoom-
            zoom_factor /= 1.5
            if zoom_factor < 0.1: zoom_factor = 0.1 # 限制最小缩放
            action_taken = True
        elif btn3_pressed: # Theme
            current_state = STATE_THEME_SELECT
            action_taken = True
    
    elif current_state == STATE_THEME_SELECT:
        if btn1_pressed: # Former
            current_theme_index = (current_theme_index - 1) % len(THEMES)
            action_taken = True
            tft.fill(THEMES[current_theme_index]["BG"])
        elif btn2_pressed: # Next
            current_theme_index = (current_theme_index + 1) % len(THEMES)
            action_taken = True
            tft.fill(THEMES[current_theme_index]["BG"])
        elif btn3_pressed: # Back
            current_state = STATE_MAIN
            action_taken = True
            tft.fill(THEMES[current_theme_index]["BG"])
    
    if action_taken:
        last_btn_press_time = time.ticks_ms()

# --- 6. 主循环 ---
def main():
    """程序主循环"""
    tft.fill(THEMES[current_theme_index]["BG"]) # 初始清屏
    
    while True:
        # 数据采集
        acquire_samples()
        
        # 参数计算
        calculate_parameters()
        
        # 处理按钮
        handle_input()
        
        # 绘制屏幕
        tft.fill(THEMES[current_theme_index]["BG"])
        draw_waveform()
        draw_ui()
        
        # 稍微延时，可要可不要
        # time.sleep_ms(20)

if __name__ == "__main__":
    main()