#include <gtest/gtest.h>

#include "mamba/core/environments_manager.hpp"

namespace mamba
{
    TEST(env_manager, all_envs)
    {
        EnvironmentsManager e;
        auto prefixes = e.list_all_known_prefixes();
        // Test registering env without `conda-meta/history` file
        e.register_env(env::expand_user("~/some/env"));
        auto new_prefixes = e.list_all_known_prefixes();
        // the prefix should be cleaned out, because it doesn't have the
        // `conda-meta/history` file
        EXPECT_EQ(new_prefixes.size(), prefixes.size());

        // Create an env containing `conda-meta/history` file
        // and test register/unregister
        auto prefix = env::expand_user("~/some_test_folder/other_env");
        path::touch(prefix / "conda-meta" / "history", true);

        e.register_env(prefix);
        new_prefixes = e.list_all_known_prefixes();
        EXPECT_EQ(new_prefixes.size(), prefixes.size() + 1);

        e.unregister_env(prefix);
        new_prefixes = e.list_all_known_prefixes();
        EXPECT_EQ(new_prefixes.size(), prefixes.size());

        // Add another file in addition to `conda-meta/history`
        // and test register/unregister
        path::touch(prefix / "conda-meta" / "other_file", true);

        e.register_env(prefix);
        new_prefixes = e.list_all_known_prefixes();
        EXPECT_EQ(new_prefixes.size(), prefixes.size() + 1);

        e.unregister_env(prefix);
        new_prefixes = e.list_all_known_prefixes();
        // Shouldn't unregister because `conda-meta/other_file`
        // is there
        EXPECT_EQ(new_prefixes.size(), prefixes.size() + 1);

        // Remove test directory
        fs::remove_all(env::expand_user("~/some_test_folder"));
    }
}  // namespace mamba
