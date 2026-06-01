#include <iostream>
#include <string>
#include <vector>

class HttpClient {
public:
    HttpClient(const std::string& baseUrl) : baseUrl_(baseUrl) {}

    std::string get(const std::string& path) {
        return buildRequest("GET", path);
    }

    std::string post(const std::string& path, const std::string& body) {
        return buildRequest("POST", path);
    }

private:
    std::string baseUrl_;
    std::vector<std::string> tags_;

    std::string buildRequest(const std::string& method, const std::string& path) {
        return method + " " + baseUrl_ + path;
    }
};

class AuthedHttpClient : public HttpClient {
public:
    AuthedHttpClient(const std::string& baseUrl, const std::string& token)
        : HttpClient(baseUrl), token_(token) {}

private:
    std::string token_;
};

struct RetryingHttpClient : HttpClient {
    int maxRetries;
};

int main() {
    HttpClient client("https://api.example.com");
    std::string response = client.get("/users");
    std::cout << response << std::endl;
    return 0;
}
