#include "tree_sitter/parser.h"
#include <string.h>
#include <wctype.h>

enum TokenType {
  NEWLINE,
  BLOCK_COMMENT,
  QUOTE,
  BACKTICK,
  TEMPLATE_CHARS,
  L_PAREN,
  R_PAREN,
  LIST_CONSTRUCTOR,
  DICT_CONSTRUCTOR,
  DECORATOR,
  DECORATOR_INLINE,
};

typedef struct ScannerState {
  int parens_nesting;
  bool in_quotes;
  bool in_backticks;
  bool eof_reported;
} ScannerState;

void *tree_sitter_rescript_external_scanner_create() {
  void* state = malloc(sizeof(ScannerState));
  memset(state, 0, sizeof(ScannerState));
  return state;
}

void tree_sitter_rescript_external_scanner_destroy(void* state) {
  free(state);
}

void tree_sitter_rescript_external_scanner_reset(void* state) {
  memset(state, 0, sizeof(ScannerState));
}

unsigned tree_sitter_rescript_external_scanner_serialize(void* state, char *buffer) {
  memcpy(buffer, state, sizeof(ScannerState));
  return sizeof(ScannerState);
}

void tree_sitter_rescript_external_scanner_deserialize(void* state, const char *buffer, unsigned n_bytes) {
  memcpy(state, buffer, n_bytes);
}

static void advance(TSLexer *lexer) { lexer->advance(lexer, false); }
static void skip(TSLexer *lexer) { lexer->advance(lexer, true); }

static bool is_inline_whitespace(int32_t c) {
  return c == ' ' || c == '\t';
}

static bool is_identifier_start(char c) {
  return c == '_' || (c >= 'a' && c <= 'z');
}

static bool is_decorator_start(char c) {
  return c == '_' || c == '\\' || (c >= 'a' && c <= 'z') || (c >= 'A' && c <= 'Z');
}

static bool is_decorator_identifier(char c) {
  return c == '_' || c == '.' || c == '\'' || (c >= 'a' && c <= 'z') || (c >= 'A' && c <= 'Z') || (c >= '0' && c <= '9');
}

static bool is_whitespace(char c) {
  return c == ' ' || c == '\t' || c == '\n' || c == '\r';
}

static void scan_whitespace(TSLexer *lexer, bool skip) {
  while (iswspace(lexer->lookahead) && !lexer->eof(lexer)) {
    lexer->advance(lexer, skip);
  }
}

// Tries to skip a line comment (//) starting at the current position.
// Returns true if a line comment was consumed. Block comments are intentionally
// NOT handled here: they are external tokens that must be left for the
// BLOCK_COMMENT scanner handler.
static bool skip_line_comment(TSLexer *lexer) {
  if (lexer->lookahead != '/') return false;
  skip(lexer);  // advance past first '/'
  if (lexer->lookahead != '/') return false;  // not a line comment
  while (lexer->lookahead != '\n' && !lexer->eof(lexer)) {
    skip(lexer);
  }
  return true;
}

// Skip whitespace and line comments only, all as skip=true.
// Used for NEWLINE peek-ahead: block comments are external tokens and must
// not be consumed here, otherwise the BLOCK_COMMENT handler never fires.
static void skip_whitespace_and_line_comments(TSLexer *lexer) {
  while (!lexer->eof(lexer)) {
    scan_whitespace(lexer, true);
    if (!skip_line_comment(lexer)) break;
  }
}

bool tree_sitter_rescript_external_scanner_scan(
    void* payload,
    TSLexer* lexer,
    const bool* valid_symbols
    ) {
  ScannerState* state = (ScannerState*)payload;
  bool in_string = state->in_quotes || state->in_backticks;

  while (is_inline_whitespace(lexer->lookahead) && !in_string) {
    skip(lexer);
  }

  if (valid_symbols[TEMPLATE_CHARS]) {
    lexer->result_symbol = TEMPLATE_CHARS;
    for (bool has_content = false;; has_content = true) {
      lexer->mark_end(lexer);
      switch (lexer->lookahead) {
        case '`':
          state->in_backticks = false;
          return has_content;
        case '\0':
          return false;
        case '$':
          advance(lexer);
          if (lexer->lookahead == '{' || is_identifier_start(lexer->lookahead)) {
            return has_content;
          }
          break;
        case '\\':
          return has_content;
        default:
          advance(lexer);
      }
    }

    return true;
  }

  // If a source file missing EOL at EOF, give the last statement a chance:
  // report the statement delimiting EOL at the very end of file. Make sure
  // it’s done only once, otherwise the scanner will enter dead-lock because
  // we report NEWLINE again and again, no matter the lexer is exhausted
  // already.
  if (valid_symbols[NEWLINE] && lexer->eof(lexer) && !state->eof_reported) {
    lexer->result_symbol = NEWLINE;
    state->eof_reported = true;
    return true;
  }

  // Handle significant newlines. A newline can act as a statement delimiter,
  // but some constructs continue over newlines (e.g. before `->`, `|`,
  // `else`, `with`, etc.). To decide, we peek ahead past any whitespace and
  // comments. Line comments (`// ...`) are grammar-level extras — if the
  // newline is significant we still want the parser to capture them, so we
  // only peek across them without advancing past the mark_end boundary.
  if (valid_symbols[NEWLINE] && lexer->lookahead == '\n') {
    lexer->advance(lexer, true);
    lexer->mark_end(lexer);

    // Peek past whitespace and line comments to determine whether the next
    // meaningful character continues the current statement.
    // Block comments are NOT skipped here: they are external tokens and must
    // be left for the BLOCK_COMMENT handler in a subsequent scanner call.
    skip_whitespace_and_line_comments(lexer);

    bool in_multiline_statement = false;
    if (lexer->lookahead == '-') {
      advance(lexer);
      if (lexer->lookahead == '>') {
        // Ignore new lines before pipe operator (->)
        in_multiline_statement = true;
      }
    } else if (lexer->lookahead == '|') {
      // Ignore new lines before variant declarations and switch matches
      in_multiline_statement = true;
    } else if (lexer->lookahead == '?' || lexer->lookahead == ':') {
      // Ignore new lines before potential ternaries
      in_multiline_statement = true;
    } else if (lexer->lookahead == '}') {
      // Do not report new lines right before block/switch closings to avoid
      // parser confusion between a terminated and unterminated statements
      // for rules like seq(repeat($._statement), $.statement)
      in_multiline_statement = true;
    } else if (lexer->lookahead == 'a') {
      advance(lexer);
      if (lexer->lookahead == 'n') {
        advance(lexer);
        if (lexer->lookahead == 'd') {
          advance(lexer);
          if (is_whitespace(lexer->lookahead)) {
            // Ignore new lines before `and` keyword (recursive definition)
            in_multiline_statement = true;
          }
        }
      }
    } else if (lexer->lookahead == 'e') {
      advance(lexer);
      if (lexer->lookahead == 'l') {
        advance(lexer);
        if (lexer->lookahead == 's') {
          advance(lexer);
          if (lexer->lookahead == 'e') {
            // Ignore new lines before `else` keyword (else/else if clauses)
            in_multiline_statement = true;
          }
        }
      }
    } else if (lexer->lookahead == 'w') {
      advance(lexer);
      if (lexer->lookahead == 'i') {
        advance(lexer);
        if (lexer->lookahead == 't') {
          advance(lexer);
          if (lexer->lookahead == 'h') {
            // Ignore new lines before `with` keyword (module type constraints)
            in_multiline_statement = true;
          }
        }
      }
    }

    if (!in_multiline_statement) {
      lexer->result_symbol = NEWLINE;
      return true;
    }
    // In a multi-line statement: fall through without emitting NEWLINE.
  }

  if (!in_string) {
    scan_whitespace(lexer, true);
  }

  // Block comments encountered at an arbitrary position (e.g. mid-expression).
  // These are emitted as BLOCK_COMMENT tokens and captured via grammar extras.
  if (valid_symbols[BLOCK_COMMENT] && lexer->lookahead == '/' && !in_string) {
    advance(lexer);
    if (lexer->lookahead == '*') {
      int level = 1;
      advance(lexer); // '*'
      while (level > 0 && !lexer->eof(lexer)) {
        switch (lexer->lookahead) {
          case '/':
            advance(lexer);
            if (lexer->lookahead == '*') {
              ++level;
              advance(lexer);
            }
            break;
          case '*':
            advance(lexer);
            if (lexer->lookahead == '/') {
              --level;
              advance(lexer);
            }
            break;
          default:
            advance(lexer);
        }
      }
      lexer->result_symbol = BLOCK_COMMENT;
      lexer->mark_end(lexer);
      return true;
    }
    // Not a block comment — fall through to other checks.
    return false;
  }

  if (valid_symbols[QUOTE] && lexer->lookahead == '"') {
    state->in_quotes = !state->in_quotes;
    lexer->result_symbol = QUOTE;
    lexer->advance(lexer, false);
    lexer->mark_end(lexer);
    return true;
  }

  if (valid_symbols[BACKTICK] && lexer->lookahead == '`') {
    state->in_backticks = !state->in_backticks;
    lexer->result_symbol = BACKTICK;
    lexer->advance(lexer, false);
    lexer->mark_end(lexer);
    return true;
  }

  if (valid_symbols[L_PAREN] && lexer->lookahead == '(') {
    ++state->parens_nesting;
    lexer->result_symbol = L_PAREN;
    lexer->advance(lexer, false);
    lexer->mark_end(lexer);
    return true;
  }

  if (valid_symbols[R_PAREN] && lexer->lookahead == ')') {
    --state->parens_nesting;
    lexer->result_symbol = R_PAREN;
    lexer->advance(lexer, false);
    lexer->mark_end(lexer);
    return true;
  }

  if (valid_symbols[LIST_CONSTRUCTOR]) {
    lexer->result_symbol = LIST_CONSTRUCTOR;
    if (lexer->lookahead == 'l') {
      advance(lexer);
      if (lexer->lookahead == 'i') {
        advance(lexer);
        if (lexer->lookahead == 's') {
          advance(lexer);
          if (lexer->lookahead == 't') {
            advance(lexer);
            if (lexer->lookahead == '{') {
              lexer->mark_end(lexer);
              return true;
            }
          }
        }
      }
    }
  }

  if (valid_symbols[DICT_CONSTRUCTOR]) {
    lexer->result_symbol = DICT_CONSTRUCTOR;
    if (lexer->lookahead == 'd') {
      advance(lexer);
      if (lexer->lookahead == 'i') {
        advance(lexer);
        if (lexer->lookahead == 'c') {
          advance(lexer);
          if (lexer->lookahead == 't') {
            advance(lexer);
            if (lexer->lookahead == '{') {
              lexer->mark_end(lexer);
              return true;
            }
          }
        }
      }
    }
  }

  if (valid_symbols[DECORATOR] && valid_symbols[DECORATOR_INLINE] && lexer->lookahead == '@') {
    advance(lexer);
    if (lexer->lookahead == '@') {
      advance(lexer);
    }

    if (is_decorator_start(lexer->lookahead)) {
      advance(lexer);

      if (lexer->lookahead == '"') {
        advance(lexer);
        while (lexer->lookahead != '"') {
          advance(lexer);
          if (lexer->eof(lexer)) {
            return false;
          }
        }
        advance(lexer);
        if (is_whitespace(lexer->lookahead)) {
          lexer->result_symbol = DECORATOR_INLINE;
          lexer->mark_end(lexer);
          return true;
        }
        if (lexer -> lookahead == '(') {
          lexer->result_symbol = DECORATOR;
          lexer->mark_end(lexer);
          return true;
        }
        return false;
      }

      while (is_decorator_identifier(lexer->lookahead)) {
        advance(lexer);
        if (lexer->eof(lexer)) {
          return false;
        }
      }

      if (is_whitespace(lexer->lookahead)) {
        lexer->result_symbol = DECORATOR_INLINE;
        lexer->mark_end(lexer);
        return true;
      }

      if (lexer->lookahead == '(') {
          lexer->result_symbol = DECORATOR;
          lexer->mark_end(lexer);
          return true;
      }
    }
    return false;
  }

  lexer->advance(lexer, iswspace(lexer->lookahead));
  return false;
}

// vim:sw=2
