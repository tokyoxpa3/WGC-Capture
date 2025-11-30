#include "pch.h" // 若無預編譯頭請刪除或註解

// 標準 Windows 標頭
#define WIN32_LEAN_AND_MEAN
#include <windows.h>
#include <d3d11.h>
#include <dxgi1_2.h>
#include <inspectable.h> 

// C++/WinRT 標頭
#include <winrt/Windows.Foundation.h>
#include <winrt/Windows.Foundation.Metadata.h>
#include <winrt/Windows.System.h>
#include <winrt/Windows.Graphics.Capture.h>
#include <winrt/Windows.Graphics.DirectX.h>
#include <winrt/Windows.Graphics.DirectX.Direct3D11.h>

#include <atomic>
#include <mutex>
#include <condition_variable>

// 鏈接必要的庫
#pragma comment(lib, "d3d11.lib")
#pragma comment(lib, "dxgi.lib")
#pragma comment(lib, "windowsapp.lib")

using namespace winrt;
namespace WGC = winrt::Windows::Graphics::Capture;
namespace WGD = winrt::Windows::Graphics::DirectX;
namespace WGD3D = winrt::Windows::Graphics::DirectX::Direct3D11;

// =============================================================
// 手動定義 Interop 介面 (修正：加上 __declspec(uuid) 以解決 C2787)
// =============================================================

// 1. IGraphicsCaptureItemInterop
// 加上 __declspec(uuid) 讓編譯器知道這個 struct 的 GUID
struct __declspec(uuid("3628E81B-3CAC-4C60-B7F4-23CE0E0C3356")) IGraphicsCaptureItemInterop : IUnknown
{
    virtual HRESULT STDMETHODCALLTYPE CreateForWindow(
        HWND window,
        REFIID riid,
        void** result) = 0;

    virtual HRESULT STDMETHODCALLTYPE CreateForMonitor(
        HMONITOR monitor,
        REFIID riid,
        void** result) = 0;
};

// 2. IDirect3DDxgiInterfaceAccess
struct __declspec(uuid("A9B3D012-3DF2-4EE3-B8D1-8695F457D3C1")) IDirect3DDxgiInterfaceAccess : IUnknown
{
    virtual HRESULT STDMETHODCALLTYPE GetInterface(
        REFIID iid,
        void** p) = 0;
};

// =============================================================
// 輔助函數
// =============================================================

// 創建 CaptureItem
WGC::GraphicsCaptureItem CreateCaptureItemForWindow(HWND hwnd) {
    auto activation_factory = get_activation_factory<WGC::GraphicsCaptureItem>();

    // 這裡調用 as<T>() 現在會成功，因為 T 已經有了 __declspec(uuid)
    auto interop_factory = activation_factory.as<IGraphicsCaptureItemInterop>();

    WGC::GraphicsCaptureItem item = { nullptr };
    check_hresult(interop_factory->CreateForWindow(hwnd, winrt::guid_of<WGC::GraphicsCaptureItem>(), winrt::put_abi(item)));
    return item;
}

// 創建 WinRT D3D Device
WGD3D::IDirect3DDevice CreateD3DDevice(IDXGIDevice* dxgi_device) {

    // 定義函數指針類型
    using PFN_CreateDirect3D11DeviceFromDXGIDevice = HRESULT(WINAPI*)(IDXGIDevice*, IInspectable**);

    static PFN_CreateDirect3D11DeviceFromDXGIDevice pCreateDirect3D11DeviceFromDXGIDevice = nullptr;

    // 首次調用時載入 DLL
    if (!pCreateDirect3D11DeviceFromDXGIDevice) {
        HMODULE hMod = LoadLibraryW(L"d3d11.dll");
        if (hMod) {
            pCreateDirect3D11DeviceFromDXGIDevice = (PFN_CreateDirect3D11DeviceFromDXGIDevice)GetProcAddress(hMod, "CreateDirect3D11DeviceFromDXGIDevice");
        }
    }

    if (pCreateDirect3D11DeviceFromDXGIDevice) {
        IInspectable* pInspectable = nullptr;
        check_hresult(pCreateDirect3D11DeviceFromDXGIDevice(dxgi_device, &pInspectable));

        WGD3D::IDirect3DDevice device = { nullptr };
        winrt::attach_abi(device, pInspectable);
        return device;
    }

    throw winrt::hresult_error(E_FAIL, L"Failed to locate CreateDirect3D11DeviceFromDXGIDevice");
}

extern "C" __declspec(dllexport) bool CaptureWindow(HWND hwnd, uint8_t* outputBuffer, int width, int height) {
    try {
        winrt::init_apartment(apartment_type::multi_threaded);
    }
    catch (...) {}

    // 1. 創建 D3D11 設備
    com_ptr<ID3D11Device> d3d11Device;
    com_ptr<ID3D11DeviceContext> d3d11Context;
    D3D_FEATURE_LEVEL featureLevel;

    // 務必使用 BGRA Support
    HRESULT hr = D3D11CreateDevice(
        nullptr, D3D_DRIVER_TYPE_HARDWARE, nullptr,
        D3D11_CREATE_DEVICE_BGRA_SUPPORT,
        nullptr, 0, D3D11_SDK_VERSION,
        d3d11Device.put(), &featureLevel, d3d11Context.put()
    );

    if (FAILED(hr)) return false;

    auto dxgiDevice = d3d11Device.as<IDXGIDevice>();

    WGD3D::IDirect3DDevice device = nullptr;
    try {
        device = CreateD3DDevice(dxgiDevice.get());
    }
    catch (...) {
        return false;
    }

    // 2. 獲取 Capture Item
    WGC::GraphicsCaptureItem item = nullptr;
    try {
        item = CreateCaptureItemForWindow(hwnd);
    }
    catch (...) {
        return false;
    }
    if (!item) return false;

    // 3. 建立 FramePool
    auto framePool = WGC::Direct3D11CaptureFramePool::CreateFreeThreaded(
        device,
        WGD::DirectXPixelFormat::B8G8R8A8UIntNormalized,
        1,
        item.Size());

    auto session = framePool.CreateCaptureSession(item);

    // 嘗試關閉黃色邊框
    if (winrt::Windows::Foundation::Metadata::ApiInformation::IsPropertyPresent(
        L"Windows.Graphics.Capture.GraphicsCaptureSession", L"IsBorderRequired"))
    {
        session.IsBorderRequired(false);
    }

    // 同步物件
    std::mutex mtx;
    std::condition_variable cv;
    bool frameReceived = false;
    com_ptr<ID3D11Texture2D> capturedTexture = nullptr;

    auto token = framePool.FrameArrived([&](WGC::Direct3D11CaptureFramePool const& sender, winrt::Windows::Foundation::IInspectable const&) {
        auto frame = sender.TryGetNextFrame();
        if (!frame) return;

        auto surface = frame.Surface();

        // 這裡調用 as<T>() 現在會成功
        auto surfaceInterop = surface.as<IDirect3DDxgiInterfaceAccess>();

        com_ptr<ID3D11Texture2D> tex2d;
        surfaceInterop->GetInterface(winrt::guid_of<ID3D11Texture2D>(), put_abi(tex2d));

        if (tex2d) {
            D3D11_TEXTURE2D_DESC desc;
            tex2d->GetDesc(&desc);

            D3D11_TEXTURE2D_DESC stagingDesc = desc;
            stagingDesc.Usage = D3D11_USAGE_STAGING;
            stagingDesc.BindFlags = 0;
            stagingDesc.CPUAccessFlags = D3D11_CPU_ACCESS_READ;
            stagingDesc.MiscFlags = 0;

            if (SUCCEEDED(d3d11Device->CreateTexture2D(&stagingDesc, nullptr, capturedTexture.put()))) {
                d3d11Context->CopyResource(capturedTexture.get(), tex2d.get());
                {
                    std::unique_lock<std::mutex> lock(mtx);
                    frameReceived = true;
                }
                cv.notify_one();
            }
        }
        });

    session.StartCapture();

    // 等待
    bool success = false;
    {
        std::unique_lock<std::mutex> lock(mtx);
        if (cv.wait_for(lock, std::chrono::seconds(2), [&] { return frameReceived; })) {
            success = true;
        }
    }

    session.Close();
    framePool.Close();

    if (success && capturedTexture) {
        D3D11_MAPPED_SUBRESOURCE mapped;
        if (SUCCEEDED(d3d11Context->Map(capturedTexture.get(), 0, D3D11_MAP_READ, 0, &mapped))) {
            uint8_t* src = static_cast<uint8_t*>(mapped.pData);
            uint8_t* dst = outputBuffer;

            int copyW = item.Size().Width;
            int copyH = item.Size().Height;
            int actualW = (width < copyW) ? width : copyW;
            int actualH = (height < copyH) ? height : copyH;

            int bytesPerPixel = 4;
            int rowPitch = mapped.RowPitch;
            int copyBytes = actualW * bytesPerPixel;

            for (int y = 0; y < actualH; ++y) {
                memcpy(dst + (y * width * bytesPerPixel), src + (y * rowPitch), copyBytes);
            }

            d3d11Context->Unmap(capturedTexture.get(), 0);
            return true;
        }
    }

    return false;
}