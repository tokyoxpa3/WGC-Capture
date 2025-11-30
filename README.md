# Windows Graphics Capture (WGC) 截圖庫

這是一個使用 Windows Graphics Capture API 實現的視窗截圖庫，可以截取特定視窗的內容並輸出為圖像數據。

## 功能特性

- 使用 Windows Graphics Capture API 進行視窗截圖
- 支援多線程截圖
- 可以根據進程名稱自動查找並截取對應視窗
- 自動處理最小化視窗的恢復和恢復原狀態
- 支援 DPI 感知

## 技術架構

### C++ 部分 (WGC.dll)
- 使用 C++/WinRT 實現 Windows Graphics Capture 功能
- 匯出 `CaptureWindow` 函數供外部調用
- 使用 Direct3D 11 進行圖像捕獲
- 通過 COM 介面與 Windows Graphics Capture API 交互

### Python 部分
- 提供 Python 綁定，使用 ctypes 調用 DLL
- 包含單視窗截圖 (`test_wgc.py`) 和多視窗截圖 (`test_multi_wgc_screenshot.py`) 的範例
- 自動尋找指定進程的視窗句柄
- 支援多線程並行截圖

## 使用方法

### 編譯
1. 使用 Visual Studio 開啟 `WGC.sln`
2. 編譯專案以生成 `WGC.dll`
3. 確保 DLL 輸出到 `x64/Release/` 目錄

### Python 測試
```bash
# 單視窗截圖
python test_wgc.py

# 多視窗截圖
python test_multi_wgc_screenshot.py
```

## 系統需求

- Windows 10 版本 1803 或更高版本 (需要 Windows Graphics Capture API)
- Visual Studio 2022 (用於編譯 C++ 部分)
- Python 3.x (用於 Python 測試腳本)
- C++/WinRT NuGet 套件

## API 說明

### C++ 函數
```cpp
extern "C" __declspec(dllexport) bool CaptureWindow(HWND hwnd, uint8_t* outputBuffer, int width, int height);
```
- `hwnd`: 要截取的視窗句柄
- `outputBuffer`: 輸出緩衝區，格式為 BGRA
- `width`, `height`: 輸出緩衝區的寬度和高度
- 返回值: 成功返回 true，失敗返回 false

### Python 函數
- `find_best_window(process_name)`: 根據進程名稱查找最適合截圖的視窗
- `capture_window(hwnd)`: 截取指定視窗的內容

## 注意事項

- 確保目標視窗處於可見狀態，最小化視窗可能無法正確截圖
- 需要正確設置 DPI 感知以避免截圖尺寸問題
- 有些應用程式可能因為安全限制無法被截圖

## 授權

本項目採用 MIT 授權，詳見 [LICENSE](LICENSE) 檔案。