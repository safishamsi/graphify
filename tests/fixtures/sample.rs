use std::collections::HashMap;

struct Graph {
    nodes: HashMap<String, Vec<String>>,
}

impl Graph {
    fn new() -> Self {
        Graph { nodes: HashMap::new() }
    }

    fn add_node(&mut self, id: String) {
        self.nodes.insert(id, vec![]);
    }

    fn add_edge(&mut self, src: String, tgt: String) {
        self.nodes.entry(src).or_default().push(tgt);
    }
}

fn build_graph(edges: Vec<(String, String)>) -> Graph {
    let mut g = Graph::new();
    for (src, tgt) in edges {
        g.add_edge(src, tgt);
    }
    g
}

trait Processor {
    fn run(&self);
}

trait Logger: Processor {
    fn log(&self);
}

struct Result<T> {
    value: T,
}

struct DataProcessor {
    current: Result<DataProcessor>,
}

impl Processor for DataProcessor {
    fn run(&self) {}
}

impl DataProcessor {
    fn build(input: DataProcessor) -> Result<DataProcessor> {
        Result { value: input }
    }
}
