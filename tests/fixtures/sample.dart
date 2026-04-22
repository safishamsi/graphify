import 'dart:io';
import 'package:http/http.dart' as http;
import '../models/user.dart';

export 'src/client.dart';

part 'sample.g.dart';

typedef Callback = void Function(int value);

enum Status { active, inactive, pending }

abstract class Animal {
  String get name;
  void speak();
}

class Dog extends Animal {
  @override
  String get name => 'Dog';

  @override
  void speak() {
    print('Woof!');
  }
}

mixin Swimmer {
  void swim() {
    print('Swimming');
  }
}

mixin Diver on Swimmer {
  void dive() {
    print('Diving');
    swim();
  }
}

class Duck extends Animal with Swimmer, Diver {
  @override
  String get name => 'Duck';

  @override
  void speak() {
    print('Quack!');
  }
}

sealed class Shape {}

final class Circle extends Shape {
  final double radius;
  Circle(this.radius);
}

base class Square extends Shape {
  final double side;
  Square(this.side);
}

extension StringUtils on String {
  String capitalize() {
    if (isEmpty) return this;
    return '${this[0].toUpperCase()}${substring(1)}';
  }
}

class HttpClient {
  final http.Client _client;

  HttpClient(this._client);

  Future<String> fetchData(String url) async {
    final response = await _client.get(Uri.parse(url));
    return response.body;
  }
}

void main() {
  final dog = Dog();
  dog.speak();
  final duck = Duck();
  duck.swim();
  duck.dive();
  final client = HttpClient(http.Client());
  client.fetchData('https://example.com');
}
