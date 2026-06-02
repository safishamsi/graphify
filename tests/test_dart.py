import unittest
import tempfile
import sys
import textwrap
from pathlib import Path

from graphify.extract import extract_dart, _make_id, _file_stem


class TestDart(unittest.TestCase):
    def setUp(self):
        self.temp_dir = tempfile.TemporaryDirectory()
        self.temp_path = Path(self.temp_dir.name)

    def tearDown(self):
        self.temp_dir.cleanup()

    def test_universal_generic_syntax_extraction(self):
        """Test that the universal parser successfully extracts generic relationships, annotations, extensions, classes, and generic calls."""
        code_content = textwrap.dedent("""
        import 'package:flutter/material.dart';
        import 'package:flutter_bloc/flutter_bloc.dart';
        import 'package:injectable/injectable.dart';
        export 'package:flutter_bloc/flutter_bloc.dart';

        // 1. Class declarations with generics, inheritance, and implements
        @injectable
        @HiveType(typeId: 10)
        class UserBloc extends Bloc<UserEvent, UserState> with MyMixin implements Disposable {
          UserBloc() : super(InitialState());
        }


        // 2. Enum declarations
        @jsonSerializable
        enum UserRole { admin, user }

        // 3. Extensions
        extension StringExtensions on String {
          bool get isEmail => contains('@');
        }

        // 4. Top-level variables
        final authServiceProvider = Provider<AuthService>((ref) => AuthService());
        final myData = 42;

        // 5. Generic method invocations (automatically catches GetIt, Provider, BlocProvider, InheritedWidget!)
        void checkDependencies(BuildContext context) {
          final custom = context.dependOnInheritedWidgetOfExactType<CustomService>();
          final auth = context.read<AuthService>();
          final bloc = BlocProvider.of<UserBloc>(context);
          final getItService = GetIt.I<DatabaseService>();
          final locatorService = locator<api.NetworkFactory>();

        }
        """)

        file_path = self.temp_path / "test_app_bloc.dart"
        file_path.write_text(code_content, encoding="utf-8")

        result = extract_dart(file_path)

        self.assertIn("nodes", result)
        self.assertIn("edges", result)

        nodes = result["nodes"]
        edges = result["edges"]

        # A. File node check
        file_node = next(
            (n for n in nodes if n["file_type"] == "code" and n["label"] == "test_app_bloc.dart"),
            None,
        )
        self.assertIsNotNone(file_node)
        self.assertEqual(file_node["source_file"], str(file_path))

        # B. Class & Enum extraction check
        user_bloc_node = next((n for n in nodes if n["label"] == "UserBloc"), None)
        self.assertIsNotNone(user_bloc_node)
        self.assertEqual(user_bloc_node["source_file"], str(file_path))

        user_role_node = next((n for n in nodes if n["label"] == "UserRole"), None)
        self.assertIsNotNone(user_role_node)

        # C. Inherits & Generics
        # Inherits Bloc (Should be global ID "bloc" without stem, source_file is None)
        inherits_bloc = next(
            (
                e
                for e in edges
                if e["source"] == user_bloc_node["id"] and e["relation"] == "inherits"
            ),
            None,
        )
        self.assertIsNotNone(inherits_bloc)
        self.assertEqual(inherits_bloc["target"], "bloc")

        bloc_node = next((n for n in nodes if n["id"] == "bloc"), None)
        self.assertIsNotNone(bloc_node)
        self.assertIsNone(bloc_node["source_file"])

        # References UserEvent, UserState generics (Should be global IDs without stem, source_file is None)
        ref_event = next(
            (
                e
                for e in edges
                if e["source"] == user_bloc_node["id"]
                and e["relation"] == "references"
                and e["target"] == "userevent"
            ),
            None,
        )
        self.assertIsNotNone(ref_event)

        event_node = next((n for n in nodes if n["id"] == "userevent"), None)
        self.assertIsNotNone(event_node)
        self.assertIsNone(event_node["source_file"])

        ref_state = next(
            (
                e
                for e in edges
                if e["source"] == user_bloc_node["id"]
                and e["relation"] == "references"
                and e["target"] == "userstate"
            ),
            None,
        )
        self.assertIsNotNone(ref_state)

        # D. Generic Class Annotations (Should be global annotation ID, source_file is None)
        injectable_annotation = next((n for n in nodes if n["label"] == "@injectable"), None)
        self.assertIsNotNone(injectable_annotation)
        self.assertEqual(injectable_annotation["id"], "annotation_injectable")
        self.assertIsNone(injectable_annotation["source_file"])

        configures_injectable = next(
            (
                e
                for e in edges
                if e["source"] == user_bloc_node["id"]
                and e["target"] == injectable_annotation["id"]
                and e["relation"] == "configures"
            ),
            None,
        )
        self.assertIsNotNone(configures_injectable)

        # Mixin check (Should have global ID "mymixin" and implements edge)
        ref_mixin = next(
            (
                e
                for e in edges
                if e["source"] == user_bloc_node["id"]
                and e["target"] == "mymixin"
                and e["relation"] == "implements"
            ),
            None,
        )
        self.assertIsNotNone(ref_mixin)

        # E. Extensions (target class string should be global without stem, source_file is None)
        ext_node = next((n for n in nodes if n["label"] == "StringExtensions"), None)
        self.assertIsNotNone(ext_node)

        extends_string = next(
            (e for e in edges if e["source"] == ext_node["id"] and e["relation"] == "extends"), None
        )
        self.assertIsNotNone(extends_string)
        self.assertEqual(extends_string["target"], "string")

        # F. Variable declarations
        provider_var = next((n for n in nodes if n["label"] == "authServiceProvider"), None)
        self.assertIsNotNone(provider_var)

        # G. Universal Generic Invocation mappings (Auto-resolved without hardcoding packages!)
        ref_custom = next(
            (
                e
                for e in edges
                if e["source"] == file_node["id"]
                and e["target"] == "customservice"
                and e["relation"] == "references"
            ),
            None,
        )
        self.assertIsNotNone(ref_custom)

        custom_node = next((n for n in nodes if n["id"] == "customservice"), None)
        self.assertIsNotNone(custom_node)
        self.assertIsNone(custom_node["source_file"])

        ref_net = next(
            (
                e
                for e in edges
                if e["source"] == file_node["id"]
                and e["target"] == "networkfactory"
                and e["relation"] == "references"
            ),
            None,
        )
        self.assertIsNotNone(ref_net)

        # H. Imports and Exports (Should have global ID, source_file is None)
        import_node = next((n for n in nodes if n["id"] == "package_flutter_material_dart"), None)
        self.assertIsNotNone(import_node)
        self.assertIsNone(import_node["source_file"])
        self.assertEqual(import_node["label"], "package:flutter/material.dart")

        export_node = next(
            (n for n in nodes if n["id"] == "package_flutter_bloc_flutter_bloc_dart"), None
        )
        self.assertIsNotNone(export_node)
        self.assertIsNone(export_node["source_file"])
        self.assertEqual(export_node["label"], "package:flutter_bloc/flutter_bloc.dart")

        export_edge = next(
            (
                e
                for e in edges
                if e["source"] == file_node["id"]
                and e["target"] == export_node["id"]
                and e["relation"] == "exports"
            ),
            None,
        )
        self.assertIsNotNone(export_edge)

    def test_advanced_dart_features(self):
        """Test complex Dart 3+ syntax and precise Riverpod/Bloc mappings."""
        code_content = textwrap.dedent("""
        import 'package:riverpod/riverpod.dart';

        # 1. Combined Modifiers & Mixin Class
        abstract base class MyBaseClass {}
        abstract interface class MyInterface {}
        mixin class MyMixinClass {}

        # 2. Riverpod Functional & Class Providers with Codegen
        @riverpod
        class MyNotifier extends _$MyNotifier {
          @override
          String build() {
            ref.watch(anotherProvider);
            return "hello";
          }
        }

        @riverpod
        String myValue(MyValueRef ref) {
          return "world";
        }

        # 3. Late & Non-Initialized Final Fields
        class MyModel {
          late final String lateField;
          final int noInitField;
          final String initField = "init";
        }

        # 4. Records & Pattern Matching in variables
        final (int, String) typedRecord = (1, "one");
        var (recA, recB) = (10, 20);

        # 5. Records in method returns & switch expressions
        (double, double) getCoordinates() {
            var localVal = switch (typedRecord) {
              (int a, String b) => (1.0, 2.0),
              _ => (0.0, 0.0),
            };
            return localVal;
        }

        # 6. Bloc constructor event registration & emission
        class AuthBloc extends Bloc<AuthEvent, AuthState> {
          AuthBloc() : super(AuthInitial()) {
            on<AuthLogin>((event, emit) {
              emit(AuthLoading());
            });
            on<AuthLogout>((event, emit) {
              yield AuthSuccess();
            });
          }
        }

        # 7. Widget Bloc trigger & bindings
        class HomeWidget {
          void triggerLogin(BuildContext context) {
            context.read<AuthBloc>().add(AuthLogin());
          }
        }
        """)

        file_path = self.temp_path / "test_advanced.dart"
        file_path.write_text(code_content, encoding="utf-8")

        result = extract_dart(file_path)

        self.assertIn("nodes", result)
        self.assertIn("edges", result)

        nodes = result["nodes"]
        edges = result["edges"]

        # Check classes
        base_class = next((n for n in nodes if n["label"] == "MyBaseClass"), None)
        self.assertIsNotNone(base_class)

        interface_class = next((n for n in nodes if n["label"] == "MyInterface"), None)
        self.assertIsNotNone(interface_class)

        mixin_class = next((n for n in nodes if n["label"] == "MyMixinClass"), None)
        self.assertIsNotNone(mixin_class)
        # Ensure we didn't mistakenly capture a node named "class"
        class_false_positive = next((n for n in nodes if n["label"] == "class"), None)
        self.assertIsNone(class_false_positive)

        # Check late & final fields
        late_field = next((n for n in nodes if n["label"] == "lateField"), None)
        self.assertIsNotNone(late_field)

        no_init_field = next((n for n in nodes if n["label"] == "noInitField"), None)
        self.assertIsNotNone(no_init_field)

        init_field = next((n for n in nodes if n["label"] == "initField"), None)
        self.assertIsNotNone(init_field)

        # Check records & destructuring
        typed_rec = next((n for n in nodes if n["label"] == "typedRecord"), None)
        self.assertIsNotNone(typed_rec)

        rec_a = next((n for n in nodes if n["label"] == "recA"), None)
        self.assertIsNotNone(rec_a)
        rec_b = next((n for n in nodes if n["label"] == "recB"), None)
        self.assertIsNotNone(rec_b)

        # Ensure deep nested variable switch-expression 'localVal' is not extracted as a top-level define
        local_val = next((n for n in nodes if n["label"] == "localVal"), None)
        self.assertIsNone(local_val)

        # Check record-returning method
        get_coord = next((n for n in nodes if n["label"] == "getCoordinates"), None)
        self.assertIsNotNone(get_coord)

        # Check Riverpod codegen defines
        mynotifier_provider = next((n for n in nodes if n["label"] == "myNotifierProvider"), None)
        self.assertIsNotNone(mynotifier_provider)

        myvalue_provider = next((n for n in nodes if n["label"] == "myValueProvider"), None)
        self.assertIsNotNone(myvalue_provider)

        # Check Riverpod watcher references
        ref_edge = next(
            (
                e
                for e in edges
                if e["target"] == "anotherprovider" and e["relation"] == "references"
            ),
            None,
        )
        self.assertIsNotNone(ref_edge)

        # Check Bloc constructor events & emissions
        login_edge = next(
            (e for e in edges if e["target"] == "authlogin" and e["context"] == "bloc_event"), None
        )
        self.assertIsNotNone(login_edge)

        emit_edge = next(
            (e for e in edges if e["target"] == "authloading" and e["context"] == "emit_state"),
            None,
        )
        self.assertIsNotNone(emit_edge)

        # Check Widget Bloc trigger
        trigger_edge = next(
            (e for e in edges if e["target"] == "authlogin" and e["context"] == "bloc_add_event"),
            None,
        )
        self.assertIsNotNone(trigger_edge)

        lookup_edge = next(
            (e for e in edges if e["target"] == "authbloc" and e["context"] == "bloc_lookup"), None
        )
        self.assertIsNotNone(lookup_edge)

    def test_namespace_and_spaced_generics(self):
        """Test that the parser successfully handles namespaces in extends/implements, and spaces/commas in nested generic variables and methods."""
        code_content = textwrap.dedent("""
        class MyWidget extends foo.Bar<Map<String, int>> implements ui.Widget, db.Model {}

        final Map<String, int> myVar = 10;
        const List<Map<String, int>> myList = [];
        late final auth.AuthService authService;

        Map<String, Map<String, int>> myMethod(String a) {}
        auth.AuthService init() {}
        """)

        file_path = self.temp_path / "test_namespaces.dart"
        file_path.write_text(code_content, encoding="utf-8")

        result = extract_dart(file_path)
        nodes = result["nodes"]
        edges = result["edges"]

        # 1. Namespaced Extends/Implements
        widget_node = next((n for n in nodes if n["label"] == "MyWidget"), None)
        self.assertIsNotNone(widget_node)

        # Base class should be 'foo.Bar' -> normalized to 'foo_bar' or 'bar'
        extends_edge = next(
            (e for e in edges if e["source"] == widget_node["id"] and e["relation"] == "inherits"),
            None,
        )
        self.assertIsNotNone(extends_edge)
        self.assertNotEqual(extends_edge["target"], "foo")  # Ensure it didn't clip

        # 2. Spaced Generics in Variables
        self.assertIsNotNone(next((n for n in nodes if n["label"] == "myVar"), None))
        self.assertIsNotNone(next((n for n in nodes if n["label"] == "myList"), None))
        self.assertIsNotNone(next((n for n in nodes if n["label"] == "authService"), None))

        # 3. Spaced Generics & Namespaces in Methods
        self.assertIsNotNone(next((n for n in nodes if n["label"] == "myMethod"), None))
        self.assertIsNotNone(next((n for n in nodes if n["label"] == "init"), None))

    def test_dart_and_flutter_specifics(self):
        """Test typedefs, mixin on, factories, constructor DI types, and universal navigation."""
        code_content = textwrap.dedent("""
        mixin AuthMixin on BaseWidget {}
        typedef JsonMap = Map<String, dynamic>;
        extension type UserId(int value) implements Object {}
        
        class MyService {
          final AuthService api;
          MyService(this.api);
          
          factory MyService.fromJson() {}
          
          void navigate(BuildContext context) {
            context.go('/home');
            Navigator.pushNamed(context, Routes.login);
            context.router.push(ProfileRoute());
          }
        }
        """)

        file_path = self.temp_path / "test_specifics.dart"
        file_path.write_text(code_content, encoding="utf-8")

        result = extract_dart(file_path)
        nodes = result["nodes"]
        edges = result["edges"]

        # 1. Mixin 'on' relation
        auth_mixin = next((n for n in nodes if n["label"] == "AuthMixin"), None)
        self.assertIsNotNone(auth_mixin)
        inherits_base = next(
            (
                e
                for e in edges
                if e["source"] == auth_mixin["id"]
                and e["relation"] == "inherits"
                and e["target"] == "basewidget"
            ),
            None,
        )
        self.assertIsNotNone(inherits_base)

        # 2. Typedefs
        json_map = next((n for n in nodes if n["label"] == "JsonMap"), None)
        self.assertIsNotNone(json_map)

        # 3. Variable DI Type (AuthService)
        api_var = next((n for n in nodes if n["label"] == "api"), None)
        self.assertIsNotNone(api_var)
        ref_auth = next(
            (
                e
                for e in edges
                if e["target"] == "authservice"
                and e["relation"] == "references"
                and e["context"] == "variable_type"
            ),
            None,
        )
        self.assertIsNotNone(ref_auth)

        # 4. Factories
        from_json = next((n for n in nodes if n["label"] == "fromJson"), None)
        self.assertIsNotNone(from_json)

        # 5. Universal Navigation
        nav_home = next(
            (e for e in edges if e["relation"] == "navigates" and e["context"] == "route_path"),
            None,
        )
        self.assertIsNotNone(nav_home)
        nav_login = next(
            (e for e in edges if e["relation"] == "navigates" and e["context"] == "route_const"),
            None,
        )
        self.assertIsNotNone(nav_login)
        nav_profile = next(
            (e for e in edges if e["relation"] == "navigates" and e["context"] == "route_object"),
            None,
        )
        self.assertIsNotNone(nav_profile)

        # 6. Extension Types
        user_id = next((n for n in nodes if n["label"] == "UserId"), None)
        self.assertIsNotNone(user_id)
        impl_obj = next(
            (
                e
                for e in edges
                if e["source"] == user_id["id"]
                and e["relation"] == "implements"
                and e["target"] == "object"
            ),
            None,
        )
        self.assertIsNotNone(impl_obj)

    def test_roadmap_bug_fixes(self):
        """Test all 5 roadmap bug fixes (Bug A, B, C, D, E)."""
        # Create parent and part child files to test Bug D (Part of file redirect)
        parent_file = self.temp_path / "parent_lib.dart"
        parent_file.write_text("library parent_lib;\npart 'child_part.dart';", encoding="utf-8")

        child_code = textwrap.dedent("""
        part of 'parent_lib.dart';
        
        class ChildClass extends Bloc<Pair<UserEvent, MyState>, State> {}
        
        var User(name: myVar, age: myAge) = user;

        void runDI(BuildContext context) {
            final repo = locator<Repository<User>>();
            context.go('/home?id=123&type=auth');
        }
        """)
        child_file = self.temp_path / "child_part.dart"
        child_file.write_text(child_code, encoding="utf-8")

        # Parse child file and verify redirect
        result = extract_dart(child_file)
        nodes = result["nodes"]
        edges = result["edges"]

        # A. Bug D redirect: No child file node should be created in nodes
        child_node = next((n for n in nodes if n["label"] == "child_part.dart"), None)
        self.assertIsNone(child_node)

        # B. Check that defines edge source is parent file ID
        parent_fid = _make_id(str(parent_file.resolve()))
        child_class = next((n for n in nodes if n["label"] == "ChildClass"), None)
        self.assertIsNotNone(child_class)

        def_edge = next(
            (e for e in edges if e["target"] == child_class["id"] and e["relation"] == "defines"),
            None,
        )
        self.assertIsNotNone(def_edge)
        self.assertEqual(def_edge["source"], parent_fid)

        # C. Bug A safe generic inheritance commas split: check referenced generics
        # Bloc<Pair<UserEvent, MyState>, State> should reference 'Pair<UserEvent, MyState>' and 'State'
        # 'Pair<UserEvent, MyState>' will be clean matched to 'Pair' node
        pair_node = next((n for n in nodes if n["id"] == "pair"), None)
        self.assertIsNotNone(pair_node)
        state_node = next((n for n in nodes if n["id"] == "state"), None)
        self.assertIsNotNone(state_node)
        # Ensure 'MyState>' or 'UserEvent' are NOT mistakenly generated as top-level generic reference nodes from broken comma-split!
        bad_node1 = next((n for n in nodes if "mystate" in n["id"]), None)
        self.assertIsNone(bad_node1)

        # D. Bug B double generics DI lookup: locator<Repository<User>>()
        repo_node = next((n for n in nodes if n["id"] == "repository"), None)
        self.assertIsNotNone(repo_node)

        # E. Bug E object destructuring variables: myVar, myAge
        self.assertIsNotNone(next((n for n in nodes if n["label"] == "myVar"), None))
        self.assertIsNotNone(next((n for n in nodes if n["label"] == "myAge"), None))
        # Ensure "name: myVar" or ":myVar" are NOT registered as variables!
        self.assertIsNone(
            next((n for n in nodes if "name" in n["label"] or "age" in n["label"]), None)
        )

        # F. Bug C GoRouter query parameter route mapping
        nav_edge = next(
            (e for e in edges if e["relation"] == "navigates" and e["context"] == "route_path"),
            None,
        )
        self.assertIsNotNone(nav_edge)
        self.assertEqual(nav_edge["target"], "route_home_id_123_type_auth")


if __name__ == "__main__":
    unittest.main()
