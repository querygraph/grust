#[path = "/tmp/sail-native-review-ffcfbd569/examples/extensions/argentea/tests/bfs_support/mod.rs"]
mod support;
use sail_argentea_core::*;
use support::*;
fn main() {
    for algorithm in [BfsAlgorithm::Reference, BfsAlgorithm::Frontier] {
        let op=operation(1,2);
        let (res,_,_)=resources(1024*1024);
        let mut ps=parts(&op,&[0,1],&[(0,1)],options(0,algorithm),&res).unwrap();
        setup(&op,&mut ps).unwrap();
        stats(&op,&mut ps).unwrap();
        let phase=phase(&op,&ps);
        let mut cursor=ps[0].start_emission(&phase).unwrap();
        let mut discarded=0;
        while cursor.next_values().unwrap().is_some(){discarded+=1;}
        let mut completion=cursor.finish().unwrap();
        completion.sequences[0]=0;
        ps[0].finish_producer(&completion).unwrap();
        ps[0].finish(&phase).unwrap();
        stats(&op,&mut ps).unwrap();
        let phase=Round{operation:op,number:ps[0].next_phase()};
        let certified=ps[0].seal(&phase).unwrap();
        println!("algorithm={algorithm:?} discarded={discarded} certified={certified:?} rows={:?}",ps[0].state_rows().collect::<Vec<_>>());
    }
}
