import kotlinx.coroutines.delay
import kotlin.math.max

data class Config(val baseUrl: String, val timeout: Int)

class HttpClient(private val config: Config) {
    fun get(path: String): String {
        return buildRequest("GET", path)
    }

    fun post(path: String, body: String): String {
        return buildRequest("POST", path)
    }

    private fun buildRequest(method: String, path: String): String {
        return "$method ${config.baseUrl}$path"
    }
}

interface Loggable {
    fun log()
}

open class BaseProcessor

class Result<T>

class DataProcessor : BaseProcessor(), Loggable {
    var current: Result<DataProcessor> = Result()

    fun run(input: DataProcessor): Result<DataProcessor> {
        return current
    }

    override fun log() {}
}

fun createClient(baseUrl: String): HttpClient {
    val config = Config(baseUrl, 30)
    return HttpClient(config)
}
