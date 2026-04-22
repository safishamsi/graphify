import 'package:flutter/material.dart';
import 'dart:async';

abstract class Processor {
  void process();
}

mixin Logger {
  void log(String message) {
    print(message);
  }
}

class DataProcessor extends Processor with Logger {
  final List<String> items = [];

  DataProcessor();

  void addItem(String item) {
    items.add(item);
  }

  @override
  void process() {
    validate(items);
  }

  List<String> validate(List<String> data) {
    log('validating');
    return data;
  }
}

enum Status {
  active,
  inactive;

  String describe() {
    return name;
  }
}

extension StringExt on String {
  bool get isBlank => trim().isEmpty;
}

void createProcessor() {
  final p = DataProcessor();
  p.addItem('test');
  p.process();
}
