// 用 macOS 自带 Vision 框架做中文 OCR，供 fetch_wechat.py 处理长图型推文。
// 不引第三方 OCR 依赖：系统已内置识别能力，离线、免模型下载、中文质量优于 tesseract。
//
// 编译：swiftc -O tools/ocr.swift -o tools/bin/ocr
//
// 用法一（逐张识别，适合独立插图）：
//     tools/bin/ocr 图1.png 图2.png
// 用法二（切片拼接后识别，适合被切成几十片的长图）：
//     tools/bin/ocr --stitch 图1.png 图2.png ...
//     tools/bin/ocr --stitch --max-height 4000 图*.png
//
// 为什么需要拼接：公众号长图常被切成几十片，文字恰好落在接缝处会被腰斩，
// 逐张识别就会产生「\态调整」这类缺字。按累积高度拼接后再识别能大幅减少。
// 但单张过高的图 Vision 会降采样，所以按 maxHeight 分组，默认 4000px。

import AppKit
import Foundation
import ImageIO
import Vision

func load(_ path: String) -> CGImage? {
    let url = URL(fileURLWithPath: path) as CFURL
    guard let src = CGImageSourceCreateWithURL(url, nil) else { return nil }
    return CGImageSourceCreateImageAtIndex(src, 0, nil)  // 动图取首帧
}

func recognize(_ cg: CGImage) -> [String] {
    let request = VNRecognizeTextRequest()
    request.recognitionLevel = .accurate
    request.recognitionLanguages = ["zh-Hans", "en-US"]
    request.usesLanguageCorrection = true

    do {
        try VNImageRequestHandler(cgImage: cg, options: [:]).perform([request])
    } catch {
        FileHandle.standardError.write("识别失败: \(error)\n".data(using: .utf8)!)
        return []
    }

    // Vision 返回顺序不保证阅读序，按 boundingBox 垂直位置重排。
    // 坐标系原点在左下，midY 越大越靠上。
    let results = request.results ?? []
    return results
        .sorted { $0.boundingBox.midY > $1.boundingBox.midY }
        .compactMap { $0.topCandidates(1).first?.string }
}

func stitch(_ images: [CGImage]) -> CGImage? {
    let width = images.map(\.width).max() ?? 0
    let height = images.reduce(0) { $0 + $1.height }
    guard width > 0, height > 0 else { return nil }

    guard let ctx = CGContext(
        data: nil,
        width: width,
        height: height,
        bitsPerComponent: 8,
        bytesPerRow: 0,
        space: CGColorSpaceCreateDeviceRGB(),
        bitmapInfo: CGImageAlphaInfo.premultipliedLast.rawValue
    ) else { return nil }

    // 白底：部分切片是透明 PNG，不铺底会识别出乱码。
    ctx.setFillColor(CGColor(red: 1, green: 1, blue: 1, alpha: 1))
    ctx.fill(CGRect(x: 0, y: 0, width: CGFloat(width), height: CGFloat(height)))
    ctx.interpolationQuality = .high

    // CGContext 原点在左下，从顶部向下逐张绘制。
    var y = CGFloat(height)
    for img in images {
        y -= CGFloat(img.height)
        let x = (CGFloat(width) - CGFloat(img.width)) / 2
        ctx.draw(img, in: CGRect(x: x, y: y, width: CGFloat(img.width), height: CGFloat(img.height)))
    }
    return ctx.makeImage()
}

var stitchMode = false
var maxHeight = 4000
var paths: [String] = []

let argv = Array(CommandLine.arguments.dropFirst())
var i = 0
while i < argv.count {
    switch argv[i] {
    case "--stitch":
        stitchMode = true
    case "--max-height":
        i += 1
        if i < argv.count { maxHeight = Int(argv[i]) ?? 4000 }
    case "-h", "--help":
        print("用法: ocr [--stitch] [--max-height N] <图片>...")
        exit(0)
    default:
        paths.append(argv[i])
    }
    i += 1
}

if paths.isEmpty {
    FileHandle.standardError.write("用法: ocr [--stitch] [--max-height N] <图片>...\n".data(using: .utf8)!)
    exit(64)
}

if stitchMode {
    var groups: [[CGImage]] = []
    var current: [CGImage] = []
    var acc = 0
    for path in paths {
        guard let cg = load(path) else {
            FileHandle.standardError.write("无法读取: \(path)\n".data(using: .utf8)!)
            continue
        }
        if !current.isEmpty && acc + cg.height > maxHeight {
            groups.append(current)
            current = []
            acc = 0
        }
        current.append(cg)
        acc += cg.height
    }
    if !current.isEmpty { groups.append(current) }

    for (index, group) in groups.enumerated() {
        print("###GROUP:\(index + 1)/\(groups.count)")
        guard let image = stitch(group) else { continue }
        for line in recognize(image) { print(line) }
    }
} else {
    for path in paths {
        print("###FILE:\(path)")
        guard let cg = load(path) else { continue }
        for line in recognize(cg) { print(line) }
    }
}
