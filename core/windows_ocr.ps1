# Local bridge to the OCR engine included with Windows 10/11.
#
# Protocol: stdin receives one base64-encoded PNG per line. stdout returns one
# base64-encoded UTF-8 OCR result per line, prefixed by "OK:", or a sanitized
# error prefixed by "ERROR:". Images are decoded entirely in memory.

$ErrorActionPreference = "Stop"

function Convert-ToProtocolText([string] $Prefix, [string] $Value) {
    $bytes = [System.Text.Encoding]::UTF8.GetBytes($Value)
    return $Prefix + [Convert]::ToBase64String($bytes)
}

try {
    Add-Type -AssemblyName System.Runtime.WindowsRuntime

    $script:AsTaskMethod = [System.WindowsRuntimeSystemExtensions].GetMethods() |
        Where-Object {
            $_.Name -eq "AsTask" -and
            $_.IsGenericMethod -and
            $_.GetParameters().Count -eq 1
        } |
        Select-Object -First 1

    if ($null -eq $script:AsTaskMethod) {
        throw "Windows Runtime async support is unavailable"
    }

    $script:OcrEngineType = [Windows.Media.Ocr.OcrEngine, Windows.Foundation, ContentType=WindowsRuntime]
    $script:OcrResultType = [Windows.Media.Ocr.OcrResult, Windows.Foundation, ContentType=WindowsRuntime]
    $script:BitmapDecoderType = [Windows.Graphics.Imaging.BitmapDecoder, Windows.Foundation, ContentType=WindowsRuntime]
    $script:SoftwareBitmapType = [Windows.Graphics.Imaging.SoftwareBitmap, Windows.Foundation, ContentType=WindowsRuntime]
    $script:MemoryStreamType = [Windows.Storage.Streams.InMemoryRandomAccessStream, Windows.Foundation, ContentType=WindowsRuntime]
    $script:DataWriterType = [Windows.Storage.Streams.DataWriter, Windows.Foundation, ContentType=WindowsRuntime]

    $script:OcrEngine = $script:OcrEngineType::TryCreateFromUserProfileLanguages()
    if ($null -eq $script:OcrEngine) {
        throw "No installed Windows OCR language is available"
    }
} catch {
    [Console]::Out.WriteLine((Convert-ToProtocolText "ERROR:" $_.Exception.Message))
    exit 1
}

function Wait-WindowsOperation($Operation, [Type] $ResultType) {
    $closedMethod = $script:AsTaskMethod.MakeGenericMethod($ResultType)
    $task = $closedMethod.Invoke($null, @($Operation))
    return $task.GetAwaiter().GetResult()
}

[Console]::Out.WriteLine("READY")

while ($null -ne ($request = [Console]::In.ReadLine())) {
    if ([string]::IsNullOrWhiteSpace($request)) {
        continue
    }

    $stream = $null
    $writer = $null
    $bitmap = $null
    try {
        $pngBytes = [Convert]::FromBase64String($request)
        $stream = New-Object $script:MemoryStreamType
        $output = $stream.GetOutputStreamAt(0)
        $writer = New-Object $script:DataWriterType($output)
        $writer.WriteBytes($pngBytes)
        [void](Wait-WindowsOperation $writer.StoreAsync() ([UInt32]))
        [void]$writer.DetachStream()
        $stream.Seek(0)

        $decoder = Wait-WindowsOperation (
            $script:BitmapDecoderType::CreateAsync($stream)
        ) $script:BitmapDecoderType
        $bitmap = Wait-WindowsOperation (
            $decoder.GetSoftwareBitmapAsync()
        ) $script:SoftwareBitmapType
        $result = Wait-WindowsOperation (
            $script:OcrEngine.RecognizeAsync($bitmap)
        ) $script:OcrResultType

        [Console]::Out.WriteLine((Convert-ToProtocolText "OK:" $result.Text))
    } catch {
        [Console]::Out.WriteLine((Convert-ToProtocolText "ERROR:" $_.Exception.Message))
    } finally {
        if ($null -ne $bitmap) { $bitmap.Dispose() }
        if ($null -ne $writer) { $writer.Dispose() }
        if ($null -ne $stream) { $stream.Dispose() }
    }
}
