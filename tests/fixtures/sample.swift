import Foundation
import UIKit

protocol Processor {
    func process() -> [String]
}

protocol Loggable {
    func log()
}

class BaseProcessor {}

class Result<T> {}

class DataProcessor: BaseProcessor, Processor {
    private var items: [String] = []
    var current: Result<DataProcessor> = Result<DataProcessor>()

    init() {}

    deinit {}

    func addItem(_ item: String) {
        items.append(item)
    }

    func process() -> [String] {
        return validate(items)
    }

    func run(input: DataProcessor) -> Result<DataProcessor> {
        return current
    }

    private func validate(_ data: [String]) -> [String] {
        return data.filter { !$0.isEmpty }
    }
}

struct Config {
    let baseUrl: String
    let timeout: Int

    subscript(key: String) -> String? {
        return nil
    }
}

enum NetworkError {
    case timeout
    case connectionFailed
    case unauthorized

    func describe() -> String {
        return "error"
    }
}

actor CacheManager {
    private var store: [String: String] = [:]

    func get(_ key: String) -> String? {
        return store[key]
    }
}

extension DataProcessor: Loggable {
    func log() {
        print("logging")
    }
}

extension Config {
    func isValid() -> Bool {
        return !baseUrl.isEmpty
    }
}

func createProcessor() -> DataProcessor {
    return DataProcessor()
}
