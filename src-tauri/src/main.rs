// 防止 Windows Release 构建弹出控制台窗口
#![cfg_attr(not(debug_assertions), windows_subsystem = "windows")]

fn main() {
    mangashelf_lib::run();
}
