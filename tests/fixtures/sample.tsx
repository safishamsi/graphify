function fmtDate(d: Date): string {
    return d.toISOString();
}

function fmtCount(n: number): string {
    return `${n} items`;
}

export function App() {
    const now = new Date();
    return (
        <div className="app">
            <h1>Header</h1>
            <span>{fmtDate(now)}</span>
            <span>{fmtCount(42)}</span>
        </div>
    );
}
