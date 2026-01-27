#!/usr/bin/env node
/**
 * 跨平台后端构建脚本
 * 自动处理 Windows/Linux/macOS 的差异
 */

const { execSync } = require('child_process');
const path = require('path');
const fs = require('fs');

// 平台检测
const isWindows = process.platform === 'win32';

// 路径配置
const projectRoot = path.resolve(__dirname, '../..');
const electronDir = path.resolve(__dirname, '..');
const backendDest = path.join(electronDir, 'backend');

// PyInstaller 的 --add-data 分隔符：Windows 用 ; ，其他平台用 :
const dataSep = isWindows ? ';' : ':';
const exeName = isWindows ? 'backend.exe' : 'backend';

console.log('🔧 Building Python backend...');
console.log(`   Platform: ${process.platform}`);
console.log(`   Project root: ${projectRoot}`);

try {
    // Step 1: 执行 PyInstaller
    const pyinstallerCmd = `pyinstaller --onefile --name backend --add-data "prompts${dataSep}prompts" server.py`;
    console.log(`\n📦 Running: ${pyinstallerCmd}`);

    execSync(pyinstallerCmd, {
        cwd: projectRoot,
        stdio: 'inherit',
        shell: true
    });

    // Step 2: 复制到 electron/backend
    const srcPath = path.join(projectRoot, 'dist', exeName);
    const destPath = path.join(backendDest, exeName);

    if (!fs.existsSync(srcPath)) {
        throw new Error(`Build output not found: ${srcPath}`);
    }

    // 确保目标目录存在
    if (!fs.existsSync(backendDest)) {
        fs.mkdirSync(backendDest, { recursive: true });
    }

    console.log(`\n📋 Copying ${exeName} to electron/backend/`);
    fs.copyFileSync(srcPath, destPath);

    console.log('\n✅ Backend build completed successfully!');
} catch (error) {
    console.error('\n❌ Backend build failed:', error.message);
    process.exit(1);
}
