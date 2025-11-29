//! Benchmarks for agent-gear filesystem operations

use criterion::{black_box, criterion_group, criterion_main, Criterion};
use std::path::PathBuf;
use tempfile::tempdir;

fn create_test_files(dir: &std::path::Path, count: usize) {
    for i in 0..count {
        let subdir = dir.join(format!("dir_{}", i / 100));
        std::fs::create_dir_all(&subdir).ok();
        let file = subdir.join(format!("file_{}.txt", i));
        std::fs::write(&file, format!("Content of file {}\n", i)).ok();
    }
}

fn bench_index_build(c: &mut Criterion) {
    let dir = tempdir().unwrap();
    create_test_files(dir.path(), 1000);

    c.bench_function("index_build_1k_files", |b| {
        b.iter(|| {
            let index = agent_gear::fs::index::FileIndex::new(dir.path().to_path_buf());
            index.build().unwrap();
            black_box(index)
        })
    });
}

fn bench_list(c: &mut Criterion) {
    let dir = tempdir().unwrap();
    create_test_files(dir.path(), 1000);

    let index = agent_gear::fs::index::FileIndex::new(dir.path().to_path_buf());
    index.build().unwrap();

    c.bench_function("list_all_1k_files", |b| {
        b.iter(|| {
            let result = index.list("**/*", true).unwrap();
            black_box(result)
        })
    });
}

fn bench_glob(c: &mut Criterion) {
    let dir = tempdir().unwrap();
    create_test_files(dir.path(), 1000);

    let index = agent_gear::fs::index::FileIndex::new(dir.path().to_path_buf());
    index.build().unwrap();

    c.bench_function("glob_txt_1k_files", |b| {
        b.iter(|| {
            let result = index.glob("**/*.txt").unwrap();
            black_box(result)
        })
    });
}

criterion_group!(benches, bench_index_build, bench_list, bench_glob);
criterion_main!(benches);
