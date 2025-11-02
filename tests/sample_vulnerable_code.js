/**
 * Sample vulnerable JavaScript code for testing the vulnerability analyzer
 * This file contains intentional security vulnerabilities for demonstration purposes
 */

const express = require('express');
const mysql = require('mysql');
const app = express();

// Database connection
const db = mysql.createConnection({
    host: 'localhost',
    user: 'root',
    password: 'password',
    database: 'myapp'
});

app.use(express.json());
app.use(express.urlencoded({ extended: true }));

// VULNERABILITY 1: SQL Injection
// User input is directly concatenated into SQL query
app.get('/user', (req, res) => {
    const userId = req.query.id;
    // Vulnerable: Direct string concatenation in SQL query
    const query = "SELECT * FROM users WHERE id = '" + userId + "'";

    db.query(query, (err, results) => {
        if (err) {
            res.status(500).send('Database error');
            return;
        }
        res.json(results);
    });
});

// VULNERABILITY 2: Command Injection
// User input passed directly to exec without sanitization
const { exec } = require('child_process');

app.post('/backup', (req, res) => {
    const filename = req.body.filename;
    // Vulnerable: User input directly in shell command
    exec(`tar -czf /backups/${filename}.tar.gz /data`, (error, stdout, stderr) => {
        if (error) {
            res.status(500).send('Backup failed');
            return;
        }
        res.send('Backup completed');
    });
});

// VULNERABILITY 3: XSS (Cross-Site Scripting)
// User input rendered without sanitization
app.get('/search', (req, res) => {
    const searchTerm = req.query.q;
    // Vulnerable: Directly embedding user input in HTML
    res.send(`
        <html>
            <body>
                <h1>Search Results for: ${searchTerm}</h1>
                <p>No results found</p>
            </body>
        </html>
    `);
});

// VULNERABILITY 4: Path Traversal
// File path constructed from user input without validation
const fs = require('fs');

app.get('/download', (req, res) => {
    const filename = req.query.file;
    // Vulnerable: User can access files outside intended directory
    const filePath = `/var/www/files/${filename}`;

    fs.readFile(filePath, (err, data) => {
        if (err) {
            res.status(404).send('File not found');
            return;
        }
        res.send(data);
    });
});

// VULNERABILITY 5: Insecure Authentication
// Weak password comparison and storage
app.post('/login', (req, res) => {
    const username = req.body.username;
    const password = req.body.password;

    // Vulnerable: SQL injection + plain text password
    const query = `SELECT * FROM users WHERE username = '${username}' AND password = '${password}'`;

    db.query(query, (err, results) => {
        if (err) {
            res.status(500).send('Error');
            return;
        }

        if (results.length > 0) {
            // Vulnerable: No session management, just setting a cookie
            res.cookie('user', username);
            res.send('Login successful');
        } else {
            res.send('Login failed');
        }
    });
});

// VULNERABILITY 6: Insecure Deserialization
app.post('/update-profile', (req, res) => {
    const userData = req.body.data;
    // Vulnerable: eval on user-controlled data
    const user = eval('(' + userData + ')');

    // Process user data...
    res.json({ success: true, user: user });
});

// VULNERABILITY 7: Missing Access Control
// No authentication check before sensitive operation
app.delete('/admin/user/:id', (req, res) => {
    const userId = req.params.id;
    // Vulnerable: No authentication or authorization check
    const query = `DELETE FROM users WHERE id = ${userId}`;

    db.query(query, (err) => {
        if (err) {
            res.status(500).send('Error');
            return;
        }
        res.send('User deleted');
    });
});

// VULNERABILITY 8: Information Disclosure
// Exposing sensitive error information
app.get('/api/data', (req, res) => {
    try {
        // Some operation that might fail
        const data = getSensitiveData();
        res.json(data);
    } catch (error) {
        // Vulnerable: Exposing stack trace to client
        res.status(500).json({
            error: error.message,
            stack: error.stack,
            details: error
        });
    }
});

function getSensitiveData() {
    throw new Error('Database connection failed: mysql://admin:P@ssw0rd@internal-db.company.local:3306/production');
}

const PORT = process.env.PORT || 3000;
app.listen(PORT, () => {
    console.log(`Server running on port ${PORT}`);
});
