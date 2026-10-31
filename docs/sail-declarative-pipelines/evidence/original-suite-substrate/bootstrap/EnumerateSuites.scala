package org.apache.spark.sql.pipelines.conformance

import java.lang.reflect.Modifier
import java.nio.file.{Files, Paths}
import java.util.jar.JarFile
import scala.jdk.CollectionConverters._
import scala.util.Using
import scala.util.control.NonFatal
import org.json4s.DefaultFormats
import org.json4s.jackson.Serialization.write
import org.scalatest.Suite

object EnumerateSuites {
  case class Entry(className: String, artifact: String, status: String,
      testNames: Vector[String], tags: Map[String, Set[String]], error: Option[String], positions: Map[String, String] = Map.empty, nestedSuiteIds: Vector[String] = Vector.empty)
  def main(args: Array[String]): Unit = {
    implicit val formats: DefaultFormats.type = DefaultFormats
    val loader = getClass.getClassLoader
    val rows = args.drop(1).toVector.flatMap { path =>
      Using.resource(new JarFile(path)) { jar =>
        jar.entries().asScala.map(_.getName).filter { name =>
          name.endsWith(".class") && !name.contains("$") &&
          (name.startsWith("org/apache/spark/sql/pipelines/") ||
           name.startsWith("org/apache/spark/sql/connect/pipelines/") ||
           name.startsWith("org/apache/spark/sql/hive/pipelines/"))
        }.toVector.sorted.map { name =>
          val className = name.stripSuffix(".class").replace('/', '.')
          try {
            val cls = Class.forName(className, false, loader)
            if (!classOf[Suite].isAssignableFrom(cls)) {
              Entry(className, path, "not_suite", Vector.empty, Map.empty, None)
            } else if (Modifier.isAbstract(cls.getModifiers) || cls.isInterface) {
              Entry(className, path, "abstract_suite", Vector.empty, Map.empty, None)
            } else {
              val suite = cls.getConstructor().newInstance().asInstanceOf[Suite]
              Entry(className, path, "registered", suite.testNames.toVector,
                suite.tags, None, suite.testNames.toVector.flatMap { test =>
                  suite.testDataFor(test).pos.map(pos => test -> (pos.fileName + ":" + pos.lineNumber))
                }.toMap, suite.nestedSuites.map(_.suiteId).toVector)
            }
          } catch {
            case error if NonFatal(error) || error.isInstanceOf[LinkageError] =>
              Entry(className, path, "unresolved", Vector.empty, Map.empty,
                Some(error.toString + Option(error.getCause).map("; cause=" + _).getOrElse("")))
          }
        }
      }
    }
    Files.writeString(Paths.get(args(0)), write(rows))
    println("Registered suites=" + rows.count(_.status == "registered") +
      "; runtime tests=" + rows.map(_.testNames.size).sum +
      "; unresolved classes=" + rows.count(_.status == "unresolved"))
  }
}
