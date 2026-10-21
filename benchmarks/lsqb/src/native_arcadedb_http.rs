//! Minimal HTTP/1.1 client for the ArcadeDB server API. No new dependency: a
//! persistent connection, explicit deadlines, and only the response framings
//! ArcadeDB uses (Content-Length and chunked). Credentials are never echoed.
use std::io::{BufRead, BufReader, Read, Write};
use std::net::{TcpStream, ToSocketAddrs};
use std::time::Duration;

const MAX_HEADER_BYTES: usize = 64 * 1024;
const MAX_BODY_BYTES: usize = 64 * 1024 * 1024;

pub(super) struct Response {
    pub status: u16,
    pub session: Option<String>,
    pub body: Vec<u8>,
}

impl Response {
    pub fn json(&self) -> Result<serde_json::Value, &'static str> {
        serde_json::from_slice(&self.body).map_err(|_| "ArcadeDB response is not JSON")
    }
}

pub(super) struct Connection {
    host: String,
    authorization: String,
    tag: Option<String>,
    reader: BufReader<TcpStream>,
}

pub(super) fn base64(input: &[u8]) -> String {
    const TABLE: &[u8; 64] = b"ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz0123456789+/";
    let mut output = String::with_capacity(input.len().div_ceil(3) * 4);
    for chunk in input.chunks(3) {
        let value = (u32::from(chunk[0]) << 16)
            | (u32::from(*chunk.get(1).unwrap_or(&0)) << 8)
            | u32::from(*chunk.get(2).unwrap_or(&0));
        for index in 0..4 {
            if index <= chunk.len() {
                output.push(TABLE[(value >> (18 - 6 * index) & 63) as usize] as char);
            } else {
                output.push('=');
            }
        }
    }
    output
}

/// Query tags land in server listings and logs; the lane's own tags are
/// `arcadedb-<pid>-<nanos>`, so anything else is refused before it is sent.
pub(super) fn tag(value: &str) -> Result<&str, &'static str> {
    let valid = value.len() <= 256
        && value
            .strip_prefix("arcadedb-")
            .and_then(|rest| rest.split_once('-'))
            .is_some_and(|(pid, nanos)| {
                [pid, nanos]
                    .iter()
                    .all(|part| !part.is_empty() && part.bytes().all(|byte| byte.is_ascii_digit()))
            });
    if valid {
        Ok(value)
    } else {
        Err("ArcadeDB query tag is invalid")
    }
}

/// `http://host:port` only: the server is on a private network without TLS.
pub(super) fn authority(url: &str) -> Result<String, &'static str> {
    let rest = url
        .strip_prefix("http://")
        .ok_or("ARCADEDB_URL must be http://host:port")?;
    let rest = rest.strip_suffix('/').unwrap_or(rest);
    if rest.is_empty() || rest.contains('/') || rest.contains('@') || !rest.contains(':') {
        return Err("ARCADEDB_URL must be http://host:port");
    }
    Ok(rest.to_string())
}

impl Connection {
    pub fn open(
        url: &str,
        user: &str,
        password: &str,
        timeout: Duration,
    ) -> Result<Self, &'static str> {
        let host = authority(url)?;
        let address = host
            .to_socket_addrs()
            .map_err(|_| "ArcadeDB address resolution failed")?
            .next()
            .ok_or("ArcadeDB address resolution failed")?;
        let stream = TcpStream::connect_timeout(&address, Duration::from_secs(10))
            .map_err(|_| "ArcadeDB connection failed")?;
        stream
            .set_read_timeout(Some(timeout))
            .and_then(|_| stream.set_write_timeout(Some(timeout)))
            .and_then(|_| stream.set_nodelay(true))
            .map_err(|_| "ArcadeDB socket configuration failed")?;
        Ok(Self {
            host,
            authorization: format!("Basic {}", base64(format!("{user}:{password}").as_bytes())),
            tag: None,
            reader: BufReader::new(stream),
        })
    }

    /// Every later request carries `X-ArcadeDB-Query-Tag`, so the server lists
    /// the statements (and the transaction session begun) under it.
    pub fn set_tag(&mut self, value: &str) -> Result<(), &'static str> {
        self.tag = Some(tag(value)?.to_string());
        Ok(())
    }

    fn head(
        &self,
        method: &str,
        path: &str,
        session: Option<&str>,
        framing: &str,
        content_type: &str,
    ) -> String {
        let mut head = format!(
            "{method} {path} HTTP/1.1\r\nHost: {}\r\nAuthorization: {}\r\nAccept: application/json\r\nContent-Type: {content_type}\r\n{framing}",
            self.host, self.authorization
        );
        if let Some(session) = session {
            head.push_str(&format!("arcadedb-session-id: {session}\r\n"));
        }
        if let Some(tag) = &self.tag {
            head.push_str(&format!("X-ArcadeDB-Query-Tag: {tag}\r\n"));
        }
        head.push_str("\r\n");
        head
    }

    pub fn request(
        &mut self,
        method: &str,
        path: &str,
        session: Option<&str>,
        body: &[u8],
    ) -> Result<Response, &'static str> {
        let head = self.head(
            method,
            path,
            session,
            &format!("Content-Length: {}\r\n", body.len()),
            "application/json",
        );
        let stream = self.reader.get_mut();
        stream
            .write_all(head.as_bytes())
            .and_then(|_| stream.write_all(body))
            .and_then(|_| stream.flush())
            .map_err(|_| "ArcadeDB request write failed")?;
        self.read_response()
    }

    pub fn json(
        &mut self,
        path: &str,
        session: Option<&str>,
        body: &serde_json::Value,
    ) -> Result<Response, &'static str> {
        let body = serde_json::to_vec(body).map_err(|_| "serialize ArcadeDB request failed")?;
        self.request("POST", path, session, &body)
    }

    /// Stream one request body with chunked framing. The server may answer
    /// early on a payload error; a failed write therefore still reads the
    /// response, so the reported failure is the server's, not a broken pipe.
    pub fn stream(
        &mut self,
        path: &str,
        content_type: &str,
        chunks: impl Iterator<Item = Result<Vec<u8>, &'static str>>,
    ) -> Result<Response, &'static str> {
        let head = self.head(
            "POST",
            path,
            None,
            "Transfer-Encoding: chunked\r\n",
            content_type,
        );
        let mut written = self
            .reader
            .get_mut()
            .write_all(head.as_bytes())
            .map_err(|_| "ArcadeDB request write failed");
        for chunk in chunks {
            let chunk = chunk?;
            if chunk.is_empty() || written.is_err() {
                continue;
            }
            let stream = self.reader.get_mut();
            written = stream
                .write_all(format!("{:x}\r\n", chunk.len()).as_bytes())
                .and_then(|_| stream.write_all(&chunk))
                .and_then(|_| stream.write_all(b"\r\n"))
                .map_err(|_| "ArcadeDB request write failed");
        }
        if written.is_ok() {
            let stream = self.reader.get_mut();
            let _ = stream.write_all(b"0\r\n\r\n").and_then(|_| stream.flush());
        }
        let response = self.read_response();
        match (response, written) {
            (Ok(response), _) => Ok(response),
            (Err(_), Err(error)) | (Err(error), Ok(())) => Err(error),
        }
    }

    fn read_line(&mut self, limit: &mut usize) -> Result<String, &'static str> {
        let mut line = Vec::new();
        let read = (&mut self.reader)
            .take(*limit as u64)
            .read_until(b'\n', &mut line)
            .map_err(|_| "ArcadeDB response read failed")?;
        if read == 0 || !line.ends_with(b"\n") {
            return Err("ArcadeDB response ended early");
        }
        *limit -= read;
        String::from_utf8(line)
            .map(|line| line.trim_end_matches(['\r', '\n']).to_string())
            .map_err(|_| "ArcadeDB response header is not UTF-8")
    }

    fn read_response(&mut self) -> Result<Response, &'static str> {
        let mut limit = MAX_HEADER_BYTES;
        let status_line = self.read_line(&mut limit)?;
        let status = status_line
            .strip_prefix("HTTP/1.1 ")
            .and_then(|rest| rest.get(..3))
            .and_then(|code| code.parse().ok())
            .ok_or("ArcadeDB response status is invalid")?;
        let (mut length, mut chunked, mut session) = (None, false, None);
        loop {
            let line = self.read_line(&mut limit)?;
            if line.is_empty() {
                break;
            }
            let (name, value) = line
                .split_once(':')
                .ok_or("ArcadeDB response header is invalid")?;
            let value = value.trim();
            match name.trim().to_ascii_lowercase().as_str() {
                "content-length" => {
                    length = Some(
                        value
                            .parse::<usize>()
                            .map_err(|_| "ArcadeDB content length is invalid")?,
                    )
                }
                "transfer-encoding" => chunked = value.eq_ignore_ascii_case("chunked"),
                "arcadedb-session-id" => session = Some(value.to_string()),
                _ => {}
            }
        }
        // 204/304 and 1xx responses never carry a body (RFC 9112 6.3); ArcadeDB
        // answers /api/v1/begin with 204 and no length.
        let body = if status == 204 || status == 304 || status < 200 {
            Vec::new()
        } else if chunked {
            let mut body = Vec::new();
            loop {
                let mut limit = MAX_HEADER_BYTES;
                let size = self.read_line(&mut limit)?;
                let size = usize::from_str_radix(size.split(';').next().unwrap_or("").trim(), 16)
                    .map_err(|_| "ArcadeDB chunk size is invalid")?;
                if size == 0 {
                    while !self.read_line(&mut limit)?.is_empty() {}
                    break;
                }
                if body.len() + size > MAX_BODY_BYTES {
                    return Err("ArcadeDB response is too large");
                }
                let start = body.len();
                body.resize(start + size, 0);
                self.reader
                    .read_exact(&mut body[start..])
                    .map_err(|_| "ArcadeDB response read failed")?;
                let mut crlf = [0; 2];
                self.reader
                    .read_exact(&mut crlf)
                    .map_err(|_| "ArcadeDB response read failed")?;
                if &crlf != b"\r\n" {
                    return Err("ArcadeDB chunk framing is invalid");
                }
            }
            body
        } else {
            let length = length.ok_or("ArcadeDB response has no length")?;
            if length > MAX_BODY_BYTES {
                return Err("ArcadeDB response is too large");
            }
            let mut body = vec![0; length];
            self.reader
                .read_exact(&mut body)
                .map_err(|_| "ArcadeDB response read failed")?;
            body
        };
        Ok(Response {
            status,
            session,
            body,
        })
    }
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn base64_matches_rfc_4648_vectors() {
        for (input, output) in [
            ("", ""),
            ("f", "Zg=="),
            ("fo", "Zm8="),
            ("foo", "Zm9v"),
            ("foob", "Zm9vYg=="),
            ("root:benchmark", "cm9vdDpiZW5jaG1hcms="),
        ] {
            assert_eq!(base64(input.as_bytes()), output);
        }
    }

    fn serve(responses: &'static [u8]) -> String {
        let listener = std::net::TcpListener::bind("127.0.0.1:0").unwrap();
        let address = listener.local_addr().unwrap();
        std::thread::spawn(move || {
            let (mut stream, _) = listener.accept().unwrap();
            let mut request = [0; 4096];
            let _ = stream.read(&mut request);
            stream.write_all(responses).unwrap();
        });
        format!("http://{address}")
    }

    #[test]
    fn reads_no_content_with_session_then_keeps_the_connection() {
        let url = serve(b"HTTP/1.1 204 No Content\r\narcadedb-session-id: AS-1\r\n\r\n\
            HTTP/1.1 200 OK\r\nTransfer-Encoding: chunked\r\n\r\n4\r\n{\"a\"\r\n3\r\n:1}\r\n0\r\n\r\n");
        let mut connection = Connection::open(&url, "root", "pw", Duration::from_secs(5)).unwrap();
        let begun = connection
            .request("POST", "/api/v1/begin/db", None, b"")
            .unwrap();
        assert_eq!(
            (begun.status, begun.session.as_deref(), begun.body.len()),
            (204, Some("AS-1"), 0)
        );
        let next = connection.read_response().unwrap();
        assert_eq!(next.json().unwrap(), serde_json::json!({"a": 1}));
    }

    #[test]
    fn a_body_without_length_or_chunking_is_refused() {
        let url = serve(b"HTTP/1.1 200 OK\r\n\r\n{}");
        let mut connection = Connection::open(&url, "root", "pw", Duration::from_secs(5)).unwrap();
        assert!(connection.request("GET", "/", None, b"").is_err());
    }

    #[test]
    fn only_lane_tags_reach_the_server() {
        assert_eq!(
            tag("arcadedb-12-1760000000000000000"),
            Ok("arcadedb-12-1760000000000000000")
        );
        for invalid in [
            "",
            "arcadedb-",
            "arcadedb-1-",
            "arcadedb-1-2-3",
            "neo4j-1-2",
            "arcadedb-1-2\r\nX: y",
        ] {
            assert!(tag(invalid).is_err(), "{invalid:?}");
        }
    }

    #[test]
    fn only_plain_private_endpoints_are_accepted() {
        assert_eq!(
            authority("http://172.18.0.2:2480"),
            Ok("172.18.0.2:2480".into())
        );
        assert_eq!(
            authority("http://arcadedb:2480/"),
            Ok("arcadedb:2480".into())
        );
        for invalid in [
            "https://host:2480",
            "http://host",
            "http://user:pw@host:2480",
            "http://host:2480/api",
            "host:2480",
        ] {
            assert!(authority(invalid).is_err(), "{invalid}");
        }
    }
}
