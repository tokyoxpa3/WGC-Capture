# Windows Graphics Capture (WGC) 截圖庫

這是一個使用 Windows Graphics Capture API 實現的視窗截圖庫，可以截取特定視窗的內容並輸出為圖像數據。專為 FPS 遊戲等需要高速截圖的場景優化。

## 功能特性

- 使用 Windows Graphics Capture API 進行視窗截圖
- 支援 ROI (Region of Interest) 裁切，可指定感興趣區域
- 支援 FPS 戰術模式：自動裁切至中心區域 (預設 640x640)
- 全螢幕截圖模式
- 自動處理最小化視窗的恢復和恢復原狀態
- 支援 DPI 感知
- 高效能，適合 FPS 遊戲場景

## 技術架構

### C++ 部分 (WGC.dll)
- 使用 C++/WinRT 實現 Windows Graphics Capture 功能
- 匯出 `InitCapture`, `GetLatestFrame`, `CleanupCapture` 函數供外部調用
- 使用 Direct3D 11 進行圖像捕獲
- 通過 COM 介面與 Windows Graphics Capture API 交互

### Python 部分
- 提供 Python 綁定，使用 ctypes 調用 DLL
- 實現 `WGCDriver` 類別，繼承自 `CaptureController` 介面
- 包含 `test_wgc.py` 測試程式，提供 GUI 界面選擇視窗和截圖模式
- 支援 FPS 戰術模式 (中心裁切) 和全螢幕監控模式

## 使用方法

### 編譯
1. 使用 Visual Studio 開啟 `WGC.sln`
2. 編譯專案以生成 `WGC.dll`
3. 確保 DLL 輸出到 `libs/WGC.dll`

### Python 測試
```bash
# 啟動帶有 GUI 的測試程式
python test_wgc.py
```

## 系統需求

- Windows 10 版本 1803 或更高版本 (需要 Windows Graphics Capture API)
- Visual Studio 2022 (用於編譯 C++ 部分)
- Python 3.x (用於 Python 測試腳本)
- C++/WinRT NuGet 套件
- opencv-python, pillow, numpy (Python 依賴)

## API 說明

### C++ 函數
```cpp
// 初始化截圖會話
extern "C" __declspec(dllexport) bool InitCapture(HWND hwnd, int roi_x, int roi_y, int roi_w, int roi_h);

// 獲取最新幀
extern "C" __declspec(dllexport) bool GetLatestFrame(uint8_t* outputBuffer, int bufferSize);

// 清理截圖會話 (新名稱，替代 ReleaseCapture)
extern "C" __declspec(dllexport) void CleanupCapture();
```

### Python 類別: `WGCDriver`
- `init_session(target_id, target_type)`: 初始化截圖工作階段
- `capture()`: 執行截圖，返回 PIL Image 對象
- `release()`: 釋放資源

### Python 類別: `FPS_WGCDriver` (擴展版本)
- `__init__(self, crop_mode="FULL", crop_w=640, crop_h=640)`: 支援設定裁切模式
- `crop_mode`: "FULL" (全螢幕) 或 "CENTER" (中心裁切)
- `crop_w`, `crop_h`: 裁切區域的寬度和高度

## 截圖模式

### FPS 戰術模式 (中心裁切)
- 自動裁切至指定區域 (預設 640x640) 的中心
- 適合 FPS 遊戲的準心偵測等應用
- 提高截圖速度和處理效率

### 全螢幕監控模式
- 截取完整視窗內容
- 適合一般監控或全螢幕截圖需求

## 注意事項

- 確保目標視窗處於可見狀態，最小化視窗可能無法正確截圖 (程式會自動嘗試還原)
- 有些應用程式可能因為安全限制無法被截圖
- FPS 模式下，裁切區域不會大於視窗實際尺寸
- 新版本 DLL 函數名稱已從 `ReleaseCapture` 變更為 `CleanupCapture`，程式碼已向下相容

## 授權

本項目採用 MIT 授權，詳見 [LICENSE](LICENSE) 檔案。