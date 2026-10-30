#![deny(warnings)]
trait Captured {
    fn value(&self) -> u32;
}
trait Preparation {
    fn capture<'a>(self: Box<Self>) -> Box<dyn Captured + 'a>
    where
        Self: 'a;
}
struct BorrowedPreparation<'a>(&'a u32);
struct BorrowedCaptured<'a>(&'a u32);
impl Captured for BorrowedCaptured<'_> {
    fn value(&self) -> u32 { *self.0 }
}
impl Preparation for BorrowedPreparation<'_> {
    fn capture<'a>(self: Box<Self>) -> Box<dyn Captured + 'a>
    where Self: 'a {
        Box::new(BorrowedCaptured(self.0))
    }
}
fn main() {
    let runner = 7;
    let preparation: Box<dyn Preparation + '_> = Box::new(BorrowedPreparation(&runner));
    let captured = preparation.capture();
    assert_eq!(captured.value(), 7);
}
