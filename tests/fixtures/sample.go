package main

import (
    "fmt"
    "net/http"
)

type Server struct {
    port int
}

func NewServer(port int) *Server {
    return &Server{port: port}
}

func (s *Server) Start() error {
    return http.ListenAndServe(fmt.Sprintf(":%d", s.port), nil)
}

func (s *Server) Stop() {
    fmt.Println("stopped")
}

type Logger interface {
    Log(msg string)
}

type Reader interface {
    Read() string
}

type ReaderLogger interface {
    Logger
    Reader
}

type BaseProcessor struct{}

type Result struct {
    value int
}

type DataProcessor struct {
    BaseProcessor
    current *Result
}

func (d *DataProcessor) Build(input *DataProcessor) (*Result, error) {
    return nil, nil
}

func main() {
    s := NewServer(8080)
    s.Start()
}
