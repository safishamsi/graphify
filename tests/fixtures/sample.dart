import 'dart:async';
import 'package:flutter/material.dart';

part 'sample.g.dart';

mixin Loggable {
  void log(String message) {
    print(message);
  }
}

abstract class Processor {
  void process();
}

class DataProcessor extends Processor with Loggable {
  final String name;

  DataProcessor({required this.name});

  factory DataProcessor.fromJson(Map<String, dynamic> json) {
    return DataProcessor(name: json['name']);
  }

  @override
  void process() {
    log('Processing');
    validate();
  }

  void validate() {
    print(name);
  }
}

extension StringExt on String {
  String capitalize() {
    return this[0].toUpperCase() + substring(1);
  }
}

enum Status {
  active,
  inactive;

  String describe() {
    return name.toUpperCase();
  }
}

void createProcessor() {
  final dp = DataProcessor(name: 'test');
  dp.process();
}
