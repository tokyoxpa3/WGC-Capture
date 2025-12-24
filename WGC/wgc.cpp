#include "pch.h" 

#define WIN32_LEAN_AND_MEAN
#include <windows.h>
#include <d3d11.h>
#include <dxgi1_2.h>
#include <inspectable.h> 
#include <atomic>
#include <mutex>
#include <memory> // for std::unique_ptr

// C++/WinRT Headers
#include <winrt/Windows.Foundation.h>
#include <winrt/Windows.System.h>
#include <winrt/Windows.Graphics.Capture.h>
#include <winrt/Windows.Graphics.DirectX.Direct3D11.h>

// Link libraries
#pragma comment(lib, "d3d11.lib")
#pragma comment(lib, "dxgi.lib")
#pragma comment(lib, "windowsapp.lib")

using namespace winrt;
namespace WGC = winrt::Windows::Graphics::Capture;
namespace WGD = winrt::Windows::Graphics::DirectX;
namespace WGD3D = winrt::Windows::Graphics::DirectX::Direct3D11;

// Interop Interface Definitions
struct __declspec(uuid("3628E81B-3CAC-4C60-B7F4-23CE0E0C3356")) IGraphicsCaptureItemInterop : IUnknown {
    virtual HRESULT STDMETHODCALLTYPE CreateForWindow(HWND window, REFIID riid, void** result) = 0;
    virtual HRESULT STDMETHODCALLTYPE CreateForMonitor(HMONITOR monitor, REFIID riid, void** result) = 0;
};

struct __declspec(uuid("A9B3D012-3DF2-4EE3-B8D1-8695F457D3C1")) IDirect3DDxgiInterfaceAccess : IUnknown {
    virtual HRESULT STDMETHODCALLTYPE GetInterface(REFIID iid, void** p) = 0;
};

// Global Manager Class
class CaptureManager {
public:
    ID3D11Device* d3d11Device = nullptr;
    ID3D11DeviceContext* d3d11Context = nullptr;

    WGC::GraphicsCaptureItem item = { nullptr };
    WGC::Direct3D11CaptureFramePool framePool = { nullptr };
    WGC::GraphicsCaptureSession session = { nullptr };

    ID3D11Texture2D* stagingTexture = nullptr;

    std::mutex mtx;
    bool hasNewFrame = false;

    int roi_x = 0, roi_y = 0, roi_w = 0, roi_h = 0;
    bool use_roi = false;

    ~CaptureManager() {
        Cleanup();
    }

    void Cleanup() {
        try {
            if (session) { session.Close(); session = nullptr; }
            if (framePool) { framePool.Close(); framePool = nullptr; }
            item = nullptr;

            if (stagingTexture) { stagingTexture->Release(); stagingTexture = nullptr; }
            if (d3d11Context) { d3d11Context->Release(); d3d11Context = nullptr; }
            if (d3d11Device) { d3d11Device->Release(); d3d11Device = nullptr; }
        }
        catch (...) {}
    }
};

static std::unique_ptr<CaptureManager> g_Manager;

// Helper: Create WinRT D3D Device from DXGI Device
WGD3D::IDirect3DDevice CreateWinRTDevice(IDXGIDevice* dxgi_device) {
    using PFN_CreateDirect3D11DeviceFromDXGIDevice = HRESULT(WINAPI*)(IDXGIDevice*, IInspectable**);
    static PFN_CreateDirect3D11DeviceFromDXGIDevice pFunc = nullptr;

    if (!pFunc) {
        HMODULE hMod = LoadLibraryW(L"d3d11.dll");
        if (hMod) pFunc = (PFN_CreateDirect3D11DeviceFromDXGIDevice)GetProcAddress(hMod, "CreateDirect3D11DeviceFromDXGIDevice");
    }

    if (pFunc) {
        IInspectable* pInspectable = nullptr;
        if (SUCCEEDED(pFunc(dxgi_device, &pInspectable))) {
            WGD3D::IDirect3DDevice device = { nullptr };
            winrt::attach_abi(device, pInspectable);
            return device;
        }
    }
    return nullptr;
}

// ====================================================
// Export 1: InitCapture
// ====================================================
extern "C" __declspec(dllexport) bool InitCapture(HWND hwnd, int cropX, int cropY, int cropW, int cropH) {
    if (g_Manager) g_Manager->Cleanup();
    g_Manager = std::make_unique<CaptureManager>();

    try {
        // 1. Initialize D3D11
        HRESULT hr = D3D11CreateDevice(nullptr, D3D_DRIVER_TYPE_HARDWARE, nullptr, D3D11_CREATE_DEVICE_BGRA_SUPPORT, nullptr, 0, D3D11_SDK_VERSION, &g_Manager->d3d11Device, nullptr, &g_Manager->d3d11Context);
        if (FAILED(hr)) return false;

        // Convert to DXGI -> WinRT Device
        // Fixed: Correctly query interface
        com_ptr<IDXGIDevice> dxgiDevice;
        hr = g_Manager->d3d11Device->QueryInterface(__uuidof(IDXGIDevice), dxgiDevice.put_void());
        if (FAILED(hr)) return false;

        auto device = CreateWinRTDevice(dxgiDevice.get());
        if (!device) return false;

        // 2. Create Capture Item
        auto activation_factory = get_activation_factory<WGC::GraphicsCaptureItem>();
        auto interop_factory = activation_factory.as<IGraphicsCaptureItemInterop>();
        check_hresult(interop_factory->CreateForWindow(hwnd, winrt::guid_of<WGC::GraphicsCaptureItem>(), winrt::put_abi(g_Manager->item)));

        if (!g_Manager->item) return false;

        // 3. Setup ROI
        if (cropW > 0 && cropH > 0) {
            g_Manager->use_roi = true;
            g_Manager->roi_x = cropX;
            g_Manager->roi_y = cropY;
            g_Manager->roi_w = cropW;
            g_Manager->roi_h = cropH;
        }
        else {
            g_Manager->use_roi = false;
            g_Manager->roi_w = g_Manager->item.Size().Width;
            g_Manager->roi_h = g_Manager->item.Size().Height;
        }

        // 4. Prepare Staging Texture (CPU Readable)
        D3D11_TEXTURE2D_DESC desc = {};
        desc.Width = g_Manager->roi_w;
        desc.Height = g_Manager->roi_h;
        desc.MipLevels = 1;
        desc.ArraySize = 1;
        desc.Format = DXGI_FORMAT_B8G8R8A8_UNORM;
        desc.SampleDesc.Count = 1;
        desc.Usage = D3D11_USAGE_STAGING;
        desc.CPUAccessFlags = D3D11_CPU_ACCESS_READ;
        desc.BindFlags = 0;

        hr = g_Manager->d3d11Device->CreateTexture2D(&desc, nullptr, &g_Manager->stagingTexture);
        if (FAILED(hr)) return false;

        // 5. Create FramePool & Session
        g_Manager->framePool = WGC::Direct3D11CaptureFramePool::CreateFreeThreaded(device, WGD::DirectXPixelFormat::B8G8R8A8UIntNormalized, 1, g_Manager->item.Size());
        g_Manager->session = g_Manager->framePool.CreateCaptureSession(g_Manager->item);

        // Try to disable border (Yellow border)
        try {
            g_Manager->session.IsBorderRequired(false);
        }
        catch (...) {}

        // 6. Frame Arrived Callback
        g_Manager->framePool.FrameArrived([&](WGC::Direct3D11CaptureFramePool const& sender, winrt::Windows::Foundation::IInspectable const&) {
            auto frame = sender.TryGetNextFrame();
            if (!frame) return;

            auto surface = frame.Surface();
            auto surfaceInterop = surface.as<IDirect3DDxgiInterfaceAccess>();
            com_ptr<ID3D11Texture2D> tex2d;
            surfaceInterop->GetInterface(winrt::guid_of<ID3D11Texture2D>(), put_abi(tex2d));

            if (tex2d && g_Manager->stagingTexture) {
                std::lock_guard<std::mutex> lock(g_Manager->mtx);

                if (g_Manager->use_roi) {
                    D3D11_BOX sourceRegion;
                    sourceRegion.left = g_Manager->roi_x;
                    sourceRegion.top = g_Manager->roi_y;
                    sourceRegion.front = 0;
                    sourceRegion.right = g_Manager->roi_x + g_Manager->roi_w;
                    sourceRegion.bottom = g_Manager->roi_y + g_Manager->roi_h;
                    sourceRegion.back = 1;

                    // GPU Crop
                    g_Manager->d3d11Context->CopySubresourceRegion(g_Manager->stagingTexture, 0, 0, 0, 0, tex2d.get(), 0, &sourceRegion);
                }
                else {
                    // Full Copy
                    g_Manager->d3d11Context->CopyResource(g_Manager->stagingTexture, tex2d.get());
                }

                g_Manager->hasNewFrame = true;
            }
            });

        g_Manager->session.StartCapture();
        return true;

    }
    catch (...) {
        return false;
    }
}

// ====================================================
// Export 2: GetLatestFrame
// ====================================================
extern "C" __declspec(dllexport) bool GetLatestFrame(uint8_t* outputBuffer, int bufferSize) {
    if (!g_Manager || !g_Manager->hasNewFrame) return false;

    std::lock_guard<std::mutex> lock(g_Manager->mtx);

    D3D11_MAPPED_SUBRESOURCE mapped;
    if (SUCCEEDED(g_Manager->d3d11Context->Map(g_Manager->stagingTexture, 0, D3D11_MAP_READ, 0, &mapped))) {

        uint8_t* src = static_cast<uint8_t*>(mapped.pData);
        uint8_t* dst = outputBuffer;

        int h = g_Manager->roi_h;
        int w = g_Manager->roi_w;
        int rowBytes = w * 4;

        if (bufferSize < h * rowBytes) {
            g_Manager->d3d11Context->Unmap(g_Manager->stagingTexture, 0);
            return false;
        }

        // Copy Row by Row
        for (int y = 0; y < h; ++y) {
            memcpy(dst + (y * rowBytes), src + (y * mapped.RowPitch), rowBytes);
        }

        g_Manager->d3d11Context->Unmap(g_Manager->stagingTexture, 0);
        return true;
    }
    return false;
}

// ====================================================
// Export 3: CleanupCapture (Renamed to avoid conflict)
// ====================================================
extern "C" __declspec(dllexport) void CleanupCapture() {
    if (g_Manager) {
        g_Manager->Cleanup();
        g_Manager = nullptr;
    }
}