fn main() {
    println!("vithkuqi\t{}", "\u{10570}".to_lowercase() == "\u{10597}".to_lowercase());
    println!("cyrillic_tje\t{}", "\u{1C89}".to_lowercase() == "\u{1C8A}".to_lowercase());
    println!("dotted_capital_i_vs_i\t{}", "\u{0130}".to_lowercase() == "\u{0069}".to_lowercase());
    println!("capital_i_vs_dotless_i\t{}", "\u{0049}".to_lowercase() == "\u{0131}".to_lowercase());
    println!("dotted_capital_i_vs_expansion\t{}", "\u{0130}".to_lowercase() == "\u{0069}\u{0307}".to_lowercase());
    println!("single_sigma_vs_final_sigma\t{}", "\u{03A3}".to_lowercase() == "\u{03C2}".to_lowercase());
    println!("single_sigma_vs_sigma\t{}", "\u{03A3}".to_lowercase() == "\u{03C3}".to_lowercase());
    println!("contextual_final_sigma\t{}", "\u{0041}\u{03A3}".to_lowercase() == "\u{0061}\u{03C2}".to_lowercase());
    println!("contextual_nonfinal_sigma\t{}", "\u{0041}\u{03A3}\u{0041}".to_lowercase() == "\u{0061}\u{03C3}\u{0061}".to_lowercase());
    println!("contextual_nonfinal_vs_final_sigma\t{}", "\u{0041}\u{03A3}\u{0041}".to_lowercase() == "\u{0061}\u{03C2}\u{0061}".to_lowercase());
    println!("accented_e\t{}", "\u{00C9}".to_lowercase() == "\u{00E9}".to_lowercase());
    println!("sharp_s\t{}", "\u{1E9E}".to_lowercase() == "\u{00DF}".to_lowercase());
}
