"""Enable the SQLite search extension used by Constituent on Android."""

from pythonforandroid.recipes.sqlite3 import Sqlite3Recipe


class SearchSqliteRecipe(Sqlite3Recipe):
    def get_recipe_env(self, arch=None, with_flags_in_cc=True):
        env = super().get_recipe_env(arch, with_flags_in_cc)
        env["CFLAGS"] = env.get("CFLAGS", "") + " -DSQLITE_ENABLE_FTS5"
        return env


recipe = SearchSqliteRecipe()
