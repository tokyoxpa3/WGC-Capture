# 貢獻指南

感謝您對此專案的興趣！以下是關於如何為此專案做貢獻的指南。

## 編譯專案

### 環境需求
- Windows 10 1803 或更高版本
- Visual Studio 2022 (或支援 C++20 的編譯器)
- Windows SDK 10.0.18362.0 或更高版本
- C++/WinRT NuGet 套件

### 編譯步驟
1. 開啟 `WGC.sln` 檔案
2. 選擇適當的配置 (Debug/Release) 和平台 (x64)
3. 編譯專案以生成 `WGC.dll`

### Python 測試
編譯完成後，您可以使用 Python 測試腳本：
- `test_wgc.py` - 單視窗截圖測試
- `test_multi_wgc_screenshot.py` - 多視窗截圖測試

## 程式碼結構

### C++ 部分
- `wgc.cpp` - 核心 WGC 截圖功能實現
- `dllmain.cpp` - DLL 入口點
- `pch.h/pch.cpp` - 預編譯頭

### Python 部分
- `test_wgc.py` - 單視窗截圖範例
- `test_multi_wgc_screenshot.py` - 多視窗截圖範例

## 語言規範

- 程式碼註解使用英文
- 程式碼命名使用英文
- 文件可使用中文或英文

## 問題回報

當回報問題時，請包含：
- Windows 版本
- Visual Studio 版本
- 重現問題的步驟
- 錯誤訊息或截圖

## 聯絡方式

如有任何問題，請透過 GitHub Issues 聯絡我們。