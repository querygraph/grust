mod protocol;
fn main() -> Result<(), Box<dyn std::error::Error>> {
    protocol::run(protocol::Mode::Direct)
}
