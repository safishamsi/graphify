import scala.collection.mutable.ListBuffer

case class Config(baseUrl: String, timeout: Int)

trait Loggable
abstract class BaseClient

class HttpClient(config: Config) extends BaseClient with Loggable {
  val source: Config = config

  def get(path: String): String = {
    buildRequest("GET", path)
  }

  def post(path: String, body: String): String = {
    buildRequest("POST", path)
  }

  private def buildRequest(method: String, path: String): String = {
    s"$method ${config.baseUrl}$path"
  }
}

object HttpClientFactory {
  def create(baseUrl: String): HttpClient = {
    new HttpClient(Config(baseUrl, 30))
  }
}
