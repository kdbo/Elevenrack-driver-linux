use std::{fs, path::Path};
fn copy_tree(source: &Path, target: &Path) {
    fs::create_dir_all(target).unwrap();
    for entry in fs::read_dir(source).unwrap() {
        let entry = entry.unwrap();
        let to = target.join(entry.file_name());
        if entry.file_type().unwrap().is_dir() {
            copy_tree(&entry.path(), &to);
        } else {
            fs::copy(entry.path(), to).unwrap();
        }
    }
}
fn main() {
    let source = Path::new("../../editor/src");
    let target = Path::new("../.generated");
    println!("cargo:rerun-if-changed=../../editor/src");
    println!("cargo:rerun-if-changed=../frontend/native.js");
    println!("cargo:rerun-if-changed=../frontend/readability.css");
    println!("cargo:rerun-if-changed=../../editor/assets");
    if target.exists() {
        fs::remove_dir_all(target).unwrap();
    }
    copy_tree(source, target);
    copy_tree(Path::new("../../editor/assets"), &target.join("assets"));
    for entry in fs::read_dir(target.join("js")).unwrap() {
        let path = entry.unwrap().path();
        if path.extension().is_some_and(|e| e == "js") {
            let text = fs::read_to_string(&path).unwrap();
            fs::write(path, text.replace("../assets/", "assets/")).unwrap();
        }
    }
    fs::copy("../frontend/native.js", target.join("native.js")).unwrap();
    fs::copy(
        "../frontend/readability.css",
        target.join("readability.css"),
    )
    .unwrap();
    let html = fs::read_to_string(target.join("index.html"))
        .unwrap()
        .replace("../assets/", "assets/")
        .replace(
            "</head>",
            "<link rel=\"stylesheet\" href=\"readability.css\">\n</head>",
        );
    assert!(html.contains("<head>"));
    fs::write(
        target.join("index.html"),
        html.replacen("<head>", "<head>\n<script src=\"native.js\"></script>", 1),
    )
    .unwrap();
    tauri_build::build();
}
